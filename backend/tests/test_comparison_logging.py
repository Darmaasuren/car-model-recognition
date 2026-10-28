import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX': '/api', 'API_KEY': 'test', 'CORS_ORIGINS': 'http://localhost:5173'}):
    from app.core.observability import safe_url, operation, record_id
    from app.services.comparison.compare import compare_one
    from app.services.comparison.source import image_url_for, ServiceComparisonError


class LoggingTests(unittest.TestCase):
    def test_url_redacts_credentials_query_and_fragment(self):
        self.assertEqual(safe_url('https://user:secret@host/file.jpg?token=private#secret'),
                         'https://host/file.jpg?REDACTED')
        self.assertEqual(safe_url('https://[broken'), '<invalid-url>')

    def test_invalid_url_logs_sanitized_source(self):
        with patch.dict(os.environ, {'IMAGE_BASE_URL': 'https://host/main/'}):
            with self.assertLogs('app.operations', level='ERROR') as captured:
                with self.assertRaises(ServiceComparisonError):
                    image_url_for({'full_photo': 'https://user:secret@host/file.jpg?token=private'})
        payload = json.loads(captured.records[0].getMessage())
        self.assertEqual(payload['event'], 'image.url.failed')
        self.assertNotIn('secret', str(payload))
        self.assertNotIn('private', str(payload))

    def test_record_context_is_reset_even_on_failure(self):
        with patch('app.services.comparison.compare.image_url_for', side_effect=RuntimeError('private-token')):
            with self.assertLogs('app.operations', level='ERROR') as captured:
                with self.assertRaises(RuntimeError):
                    compare_one({'_id': 'record-42'}, None)
        self.assertIsNone(record_id.get())
        payload = json.loads(captured.records[0].getMessage())
        self.assertEqual(payload['record_id'], 'record-42')
        self.assertNotIn('private-token', str(payload))

    def test_database_failure_has_record_id_without_exception_body(self):
        @operation('record.save')
        def save(record_id):
            raise RuntimeError('password=secret')
        with self.assertLogs('app.operations', level='ERROR') as captured:
            with self.assertRaises(RuntimeError):
                save('record-42')
        payload = json.loads(captured.records[0].getMessage())
        self.assertEqual(payload['record_id'], 'record-42')
        self.assertNotIn('secret', str(payload))
