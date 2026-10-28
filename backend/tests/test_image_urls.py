import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'API_PREFIX': '/api', 'API_KEY': 'test', 'CORS_ORIGINS': 'http://localhost:5173'}):
    from app.services.comparison.source import image_url_for, ServiceComparisonError
    from app.services.comparison.store import RecognitionStore


class ImageURLTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'IMAGE_BASE_URL': 'https://traffic-police.odt.mn/main/'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_absolute_and_relative_variants(self):
        tail = 'uploads/vehicles/20261013/52f109d7-a5a0-4ec8-9dac-5b862df61b06.jpg'
        expected = 'https://traffic-police.odt.mn/main/' + tail
        for prefix in ('https://traffic-police.odt.mn/file/',
                       'https://traffic-police.odt.mn/main/',
                       '/file/', 'file/', '/main/', 'main/', '/', ''):
            with self.subTest(prefix=prefix):
                record = {'_id': 'test-record', 'full_photo': prefix + tail}
                with self.assertLogs('app.operations', level='INFO') as logs:
                    self.assertEqual(image_url_for(record), expected)
                payload = json.loads(logs.records[-1].getMessage())
                self.assertEqual(payload['source_url'], record['full_photo'])
                self.assertEqual(payload['download_url'], expected)
                self.assertEqual(payload['record_id'], 'test-record')
                self.assertEqual(RecognitionStore(None).source_values(record)['source_image_path'], prefix + tail)

    def test_only_leading_prefix_is_replaced(self):
        self.assertEqual(image_url_for({'full_photo': 'file/uploads/file/main/car-file.jpg'}),
                         'https://traffic-police.odt.mn/main/uploads/file/main/car-file.jpg')

    def test_configured_base_path(self):
        with patch.dict(os.environ, {'IMAGE_BASE_URL': 'https://traffic-police.odt.mn/photos/'}):
            for path in ('file/uploads/car.jpg', 'photos/uploads/car.jpg', 'uploads/car.jpg'):
                self.assertEqual(image_url_for({'full_photo': path}),
                                 'https://traffic-police.odt.mn/photos/uploads/car.jpg')

    def test_invalid_paths(self):
        for path in (None, '', 123, 'https://other.test/file/car.jpg',
                     'http://traffic-police.odt.mn/file/car.jpg',
                     'https://traffic-police.odt.mn:444/file/car.jpg',
                     'https://user:pass@traffic-police.odt.mn/file/car.jpg',
                     '//other.test/car.jpg', '../car.jpg', 'file/../car.jpg',
                     'uploads/%2e%2e/car.jpg', 'file/%252e%252e/car.jpg',
                     'file/%2f%2fother.test/car.jpg', 'file/\\other.test/car.jpg',
                     'uploads/car.jpg?token=secret', 'uploads/car.jpg#fragment',
                     'file/', 'main/', 'file/https://other.test/a.jpg',
                     'https://[broken', 'uploads/\ncar.jpg'):
            with self.subTest(path=path), self.assertLogs('app.operations', level='ERROR'):
                with self.assertRaises(ServiceComparisonError):
                    image_url_for({'full_photo': path})
