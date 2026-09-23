import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with patch.dict(os.environ, {
    'API_PREFIX': '/api', 'API_KEY': 'test',
    'CORS_ORIGINS': 'http://localhost:5173',
}):
    from app.services.service_comparison import (
        ServiceComparisonError, compare_batch, compare_label, compare_record, fetch_record,
        image_url_for,
    )


class ServiceComparisonTests(unittest.TestCase):
    def test_fetch_sends_bearer_only_to_record_service(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.status_code = 200
        response.is_redirect = False
        response.json.return_value = {'items': [{'_id': 'one'}]}
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)
        session.request.return_value = response
        with patch.dict(os.environ, {
            'SERVICE_URL': 'https://example.test/api/record/table',
            'SERVICE_TOKEN': 'secret-token', 'SERVICE_METHOD': 'POST',
            'SERVICE_PARAMS_JSON': '{}', 'SERVICE_BODY_JSON': '{}',
        }):
            with patch('app.services.service_comparison.requests.Session', return_value=session):
                self.assertEqual(fetch_record()['_id'], 'one')
        self.assertEqual(session.request.call_args.kwargs['headers']['Authorization'],
                         'Bearer secret-token')

    def test_full_photo_is_restricted_to_relative_path(self):
        with patch.dict(os.environ, {'IMAGE_BASE_URL': 'https://example.test/main/'}):
            self.assertEqual(image_url_for({'full_photo': 'uploads/car.png'}),
                             'https://example.test/main/uploads/car.png')
            for path in ('https://other.test/car.png', '//other.test/car.png',
                         '../private.png'):
                with self.assertRaises(ServiceComparisonError):
                    image_url_for({'full_photo': path})

    def test_comparison_selects_highest_model_confidence(self):
        labels = {'model': ['Toyota Prius'], 'color': ['white', 'black'], 'type': ['car']}
        prediction = SimpleNamespace(
            model=SimpleNamespace(label='Toyota Prius', confidence=.95),
            color=SimpleNamespace(label='white', confidence=.96),
            vehicle_type=SimpleNamespace(label='car', confidence=.94),
            model_dump=lambda **kwargs: {'model': {'label': 'Toyota Prius', 'confidence': .95}},
        )
        pipeline = SimpleNamespace(
            classifier=SimpleNamespace(label_groups=labels),
            process_image=lambda frame: [prediction],
        )
        record = {'_id': 'one', 'mark': 'Toyota', 'model': 'Prius',
                  'color': 'Цагаан', 'plate': '1234АБВ'}
        result = compare_record(record, object(), pipeline)
        self.assertEqual((result['modelStatus'], result['colorStatus']), ('MATCH', 'MATCH'))
        self.assertEqual(compare_label('Honda Fit', prediction.model, labels['model']),
                         'UNSUPPORTED_CLASS')
        self.assertEqual(compare_label('Toyota Prius',
                         SimpleNamespace(label='Toyota Prius', confidence=.89),
                         labels['model']), 'LOW_CONFIDENCE')
        other = SimpleNamespace(
            model=SimpleNamespace(label='Honda Fit', confidence=.98),
            color=SimpleNamespace(label='black', confidence=.99),
            vehicle_type=SimpleNamespace(label='car', confidence=.97),
            model_dump=lambda **kwargs: {'model': {'label': 'Honda Fit', 'confidence': .98}},
        )
        missing_model = SimpleNamespace(model=None)
        for predictions in ([prediction, other, missing_model],
                            [missing_model, other, prediction]):
            pipeline.process_image = lambda frame: predictions
            with patch('app.services.service_comparison.check_seatbelt', return_value={}) as seatbelt:
                frame = object()
                result = compare_record(record, frame, pipeline)
                seatbelt.assert_called_once_with(frame, other)
            self.assertEqual(result['imageStatus'], 'OK')
            self.assertEqual(result['prediction'], other.model_dump())
            self.assertEqual(result['modelStatus'], 'MISMATCH')
            self.assertEqual(result['colorStatus'], 'MISMATCH')

        other.model.confidence = .89
        prediction.model.confidence = .85
        pipeline.process_image = lambda frame: [prediction, other]
        result = compare_record(record, object(), pipeline)
        self.assertEqual(result['imageStatus'], 'OK')
        self.assertEqual(result['modelStatus'], 'LOW_CONFIDENCE')

        pipeline.process_image = lambda frame: []
        result = compare_record(record, object(), pipeline)
        self.assertEqual(result['imageStatus'], 'NO_VEHICLE_DETECTED')
        self.assertEqual(result['modelStatus'], 'NO_VEHICLE_DETECTED')
        self.assertIsNone(result['prediction'])

    def test_batch_keeps_other_results_when_one_record_fails(self):
        records = [{'_id': str(index), 'plate': str(index)} for index in range(21)]
        def process(raw, pipeline):
            if raw['_id'] == '1':
                raise ServiceComparisonError('Missing photo')
            return {'recordId': raw['_id'], 'plate': raw['plate']}
        with patch('app.services.service_comparison.fetch_records', return_value=records[:20]):
            with patch('app.services.service_comparison.compare_one', side_effect=process):
                result = compare_batch(object())
        self.assertEqual(result['count'], 20)
        self.assertEqual(result['items'][1]['error'], 'Missing photo')
        self.assertEqual(result['items'][19]['recordId'], '19')
