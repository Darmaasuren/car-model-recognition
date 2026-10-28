"""Configuration stays centralized, injectable and compatible with worker cursors."""
import ast
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_admin_settings, get_database_settings, get_seatbelt_settings


class ConfigurationTests(unittest.TestCase):
    def test_admin_database_do_not_require_api_environment(self):
        with patch.dict(os.environ, {'DB_PASSWORD': 'secret', 'ADMIN_USERNAME': ' ADMIN ', 'ADMIN_PASSWORD': 'secret'}, clear=True):
            self.assertEqual(get_admin_settings().username, 'admin')
            self.assertEqual(get_database_settings().host, 'localhost')
            self.assertNotIn('secret', repr(get_admin_settings()))
            self.assertNotIn('secret', repr(get_database_settings()))

    def test_invalid_seatbelt_settings_fail_early(self):
        for env in [{'SEATBELT_TIMEOUT_SECONDS': 'nan'}, {'SEATBELT_TIMEOUT_SECONDS': '0'},
                    {'SEATBELT_CONFIDENCE': '1.1'}, {'SEATBELT_FRONT_VIEW_MIN_CONFIDENCE': 'nan'}]:
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    get_seatbelt_settings()

    def test_seatbelt_config_is_immutable(self):
        with patch.dict(os.environ, {}, clear=True):
            config = get_seatbelt_settings()
        with self.assertRaises(FrozenInstanceError):
            config.enabled = True

    def test_only_config_reads_environment_and_auth_has_no_duplicate_definitions(self):
        app = Path(__file__).resolve().parents[1] / 'app'
        for file in app.rglob('*.py'):
            if file == app / 'core/config.py':
                continue
            source = file.read_text()
            self.assertNotIn('os.getenv(', source, str(file))
            self.assertNotIn('os.environ', source, str(file))
        tree = ast.parse((app / 'services/auth.py').read_text())
        names = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
        self.assertEqual(len(names), len(set(names)))

    def test_worker_fingerprint_unchanged(self):
        with patch.dict(os.environ, {'API_PREFIX': '/api', 'API_KEY': 'test', 'CORS_ORIGINS': 'http://localhost:5173'}):
            from app.services.comparison.poller import PollConfig
        env = {'SERVICE_URL': 'https://example.test', 'SERVICE_METHOD': 'POST',
               'SERVICE_BODY_JSON': '{"limit": 20}', 'SERVICE_PARAMS_JSON': '{}'}
        with patch.dict(os.environ, env, clear=True):
            expected = 'latest-v1:' + sha256(json.dumps(list(env.values())).encode()).hexdigest()
            self.assertEqual(PollConfig.from_env().fingerprint, expected)
