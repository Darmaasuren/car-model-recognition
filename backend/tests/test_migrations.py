"""Fresh schema and legacy adoption must preserve data and match ORM metadata."""
import importlib.util
from pathlib import Path
import sys
import unittest

from sqlalchemy import create_engine, inspect, text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import Base, upgrade_database
import app.models.user
import app.models.recognition
import app.models.source_token
import app.models.sync_state
import app.models.video_session


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)

    def test_fresh_database_and_repeat_startup(self):
        upgrade_database(self.engine)
        upgrade_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text('SELECT version_num FROM alembic_version')), '0002_seatbelt_result')
            self.assertEqual(compare_metadata(MigrationContext.configure(connection), Base.metadata), [])

    def test_adopt_existing_database_preserves_data(self):
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO vehicle_recognitions (id, source_record_id, plate, source_mark, source_model, source_color, source_type, source_image_path, status, attempt_count, fetched_at, seatbelt_result) VALUES (1, 'event', '1234', '', '', '', '', '', 'completed', 1, CURRENT_TIMESTAMP, '{\"schemaVersion\":1}')")
        upgrade_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text('SELECT plate FROM vehicle_recognitions')), '1234')
            self.assertEqual(connection.scalar(text('SELECT seatbelt_result FROM vehicle_recognitions')), '{"schemaVersion":1}')

    def test_legacy_schema_without_seatbelt_gets_column(self):
        path = Path(__file__).resolve().parents[1] / 'migrations/versions/0001_baseline.py'
        spec = importlib.util.spec_from_file_location('baseline', path)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        baseline.metadata.create_all(self.engine)
        self.assertNotIn('seatbelt_result', {c['name'] for c in inspect(self.engine).get_columns('vehicle_recognitions')})
        upgrade_database(self.engine)
        self.assertIn('seatbelt_result', {c['name'] for c in inspect(self.engine).get_columns('vehicle_recognitions')})

    def test_unknown_schema_is_not_silently_stamped(self):
        with self.engine.begin() as connection:
            connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        with self.assertRaisesRegex(RuntimeError, 'Legacy schema differs'):
            upgrade_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text('SELECT COUNT(*) FROM alembic_version')), 0)
