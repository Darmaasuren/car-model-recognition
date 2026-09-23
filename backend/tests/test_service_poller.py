import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from unittest.mock import patch, Mock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX': '/api', 'API_KEY': 'test', 'CORS_ORIGINS': 'http://localhost:5173'}):
    from app.models.service_sync import ServiceSync
    from app.models.vehicle_recognition import VehicleRecognition as Row
    from app.services.service_poller import ServicePoller, PollConfig, aware
    from app.services.service_comparison import ServiceComparisonError, fetch_records


class PollerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        ServiceSync.__table__.create(self.engine)
        Row.__table__.create(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.now = datetime(2026, 9, 23, 3, tzinfo=timezone.utc)
        config = PollConfig('latest-v1:test')
        self.poller = ServicePoller(self.factory, object(), None, config)
        self.poller.stop = Mock(is_set=Mock(return_value=False), wait=Mock(return_value=False))
        self.clock = patch('app.services.service_poller.now_utc', side_effect=lambda: self.now)
        self.clock.start()
        self.poller.initialize()

    def tearDown(self):
        self.clock.stop()
        self.engine.dispose()

    def records(self, count=20):
        return [{'_id': str(i), 'full_photo': 'uploads/test.jpg',
                 'event_date': self.now.isoformat()} for i in range(count)]

    def state(self):
        with self.factory() as db:
            return db.get(ServiceSync, 1)

    def test_one_page_per_twenty_minutes_and_restart_keeps_due_time(self):
        with patch('app.services.service_poller.fetch_records', return_value=self.records()) as fetch, \
             patch.object(self.poller, 'process_pending'):
            self.poller.tick()
            self.assertEqual(self.state().next_offset, 0)
            self.poller.initialize()
            self.now += timedelta(seconds=1199)
            self.poller.tick()
            self.assertEqual(fetch.call_count, 1)
            self.now += timedelta(seconds=1)
            self.poller.tick()
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(fetch.call_args.kwargs['overrides']['offset'], 0)
            self.assertEqual(fetch.call_args.kwargs['overrides']['limit'], 20)
            with self.factory() as db:
                self.assertEqual(len(db.scalars(select(Row)).all()), 20)

    def test_timeout_does_not_advance_cursor(self):
        with patch('app.services.service_poller.fetch_records', side_effect=ServiceComparisonError('Timeout')):
            self.poller.tick()
        self.assertEqual(self.state().next_offset, 0)
        self.assertEqual(self.state().failures, 1)
        self.assertEqual(self.state().status, 'cooldown')

    def test_rate_limit_waits_for_retry_after(self):
        with patch('app.services.service_poller.fetch_records', side_effect=ServiceComparisonError('429', retry_after=3600)) as fetch:
            self.poller.tick()
            self.now += timedelta(seconds=1201)
            self.poller.tick()
            self.assertEqual(fetch.call_count, 1)

    def test_forbidden_blocks_new_requests(self):
        with patch('app.services.service_poller.fetch_records', side_effect=ServiceComparisonError('403', blocked=True)) as fetch:
            self.poller.tick()
            self.now += timedelta(hours=1)
            self.poller.tick()
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(self.state().status, 'blocked')

    def test_short_page_keeps_first_page_without_date_window(self):
        with patch('app.services.service_poller.fetch_records', return_value=self.records(3)), \
             patch.object(self.poller, 'process_pending'):
            self.poller.tick()
        self.assertIsNone(self.state().window_start)
        self.assertIsNone(self.state().window_end)

    def test_invalid_page_does_not_save_partial_page_or_advance(self):
        with patch('app.services.service_poller.fetch_records', return_value=[*self.records(2), {}]):
            self.poller.tick()
        self.assertEqual(self.state().status, 'blocked')
        self.assertEqual(self.state().next_offset, 0)
        with self.factory() as db:
            self.assertEqual(db.scalars(select(Row)).all(), [])

    def test_completed_not_reprocessed_and_failure_does_not_stop_batch(self):
        for record in self.records(3):
            self.poller.store.enqueue(record)
        with self.factory() as db, db.begin():
            db.scalar(select(Row).where(Row.source_record_id == '0')).status = 'completed'
        with patch('app.services.service_poller.compare_one', side_effect=RuntimeError('model error')) as compare:
            self.poller.process_pending()
        self.assertEqual(compare.call_count, 2)
        self.poller.process_pending()  # Failed records not immediately retried.
        with self.factory() as db:
            rows = db.scalars(select(Row).order_by(Row.id)).all()
            self.assertEqual([r.status for r in rows], ['completed', 'failed', 'failed'])
            self.assertEqual([r.attempt_count for r in rows], [0, 1, 1])

    def test_three_attempts_only(self):
        self.poller.store.enqueue(self.records(1)[0])
        with patch('app.services.service_poller.compare_one', side_effect=RuntimeError('model error')) as compare:
            for _ in range(5):
                self.poller.process_pending()
                # Store timestamps use actual UTC, so explicitly make retry due.
                with self.factory() as db, db.begin():
                    db.scalar(select(Row)).completed_at = self.now - timedelta(minutes=60)
            self.assertEqual(compare.call_count, 3)

    def test_recovery_and_configuration_guard(self):
        record = self.records(1)[0]
        self.poller.store.enqueue(record)
        self.poller.store.start(record)
        self.poller.initialize()
        with self.factory() as db:
            self.assertEqual(db.scalar(select(Row)).status, 'failed')
        self.poller.config = PollConfig('latest-v1:different')
        with self.assertRaises(ValueError):
            self.poller.initialize()

    def test_worker_overrides_request_pagination_and_dates(self):
        response = Mock(status_code=200, is_redirect=False)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.json.return_value = {'items': []}
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=None)
        client.request.return_value = response
        with patch.dict(os.environ, {'SERVICE_URL': 'https://example.test', 'SERVICE_TOKEN': 'test',
            'SERVICE_METHOD': 'POST', 'SERVICE_BODY_JSON': '{"offset": 9, "limit": 100, "filter": "keep"}'}), \
             patch('app.services.service_comparison.requests.Session', return_value=client):
            fetch_records(20, overrides={'offset': 2, 'limit': 20, 'startDate': 'start', 'endDate': 'end'})
        self.assertEqual(client.request.call_args.kwargs['json'],
                         {'offset': 2, 'limit': 20, 'filter': 'keep', 'startDate': 'start', 'endDate': 'end'})

    def test_upgrade_from_date_windows_preserves_history_and_delays_request(self):
        self.poller.store.enqueue(self.records(1)[0])
        with self.factory() as db, db.begin():
            state = db.get(ServiceSync, 1)
            state.config_key = "legacy-fingerprint"
            state.window_start = self.now - timedelta(hours=1)
            state.window_end = self.now
            state.next_offset = 9
        self.poller.initialize()
        self.assertIsNone(self.state().window_start)
        self.assertEqual(self.state().next_offset, 0)
        self.assertEqual(aware(self.state().next_request_at), self.now + timedelta(minutes=20))
        with self.factory() as db:
            self.assertEqual(len(db.scalars(select(Row)).all()), 1)

    def test_latest_request_strips_dates_from_body_and_query(self):
        response = Mock(status_code=200, is_redirect=False)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.json.return_value = {'items': []}
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=None)
        client.request.return_value = response
        with patch.dict(os.environ, {'SERVICE_URL': 'https://example.test', 'SERVICE_TOKEN': 'test',
            'SERVICE_METHOD': 'POST',
            'SERVICE_BODY_JSON': '{"startDate":"old","endDate":"old","offset":9,"filter":"keep"}',
            'SERVICE_PARAMS_JSON': '{"startDate":"old","endDate":"old"}'}), \
             patch('app.services.service_comparison.requests.Session', return_value=client):
            fetch_records(20, overrides={'offset': 0, 'limit': 20}, omit_date_filters=True)
        self.assertEqual(client.request.call_args.kwargs['json'], {'offset': 0, 'limit': 20, 'filter': 'keep'})
        self.assertEqual(client.request.call_args.kwargs['params'], {})
