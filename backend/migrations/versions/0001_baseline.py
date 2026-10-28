"""Initial schema, with non-destructive adoption of the pre-migration database.

This metadata is a frozen snapshot, deliberately independent of application models.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

metadata = sa.MetaData()

sa.Table('service_sync_state', metadata,
    sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.Column('window_end', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.Column('next_offset', sa.Integer(), primary_key=False, nullable=False),
    sa.Column('next_request_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.Column('status', sa.Text(), primary_key=False, nullable=False),
    sa.Column('last_error', sa.Text(), primary_key=False, nullable=True),
    sa.Column('failures', sa.Integer(), primary_key=False, nullable=False),
    sa.Column('config_key', sa.Text(), primary_key=False, nullable=True),
)

sa.Table('service_tokens', metadata,
    sa.Column('key', sa.String(length=64), primary_key=True, nullable=False),
    sa.Column('token', sa.Text(), primary_key=False, nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
)

sa.Table('users', metadata,
    sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
    sa.Column('username', sa.Text(), primary_key=False, nullable=False, unique=True),
    sa.Column('password_hash', sa.String(length=255), primary_key=False, nullable=False),
    sa.Column('role', sa.String(length=20), primary_key=False, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
    sa.CheckConstraint("role IN ('admin', 'reviewer', 'viewer')"),
)

sa.Table('vehicle_recognitions', metadata,
    sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
    sa.Column('source_record_id', sa.Text(), primary_key=False, nullable=False, unique=True),
    sa.Column('plate', sa.Text(), primary_key=False, nullable=False),
    sa.Column('event_date', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.Column('source_mark', sa.Text(), primary_key=False, nullable=False),
    sa.Column('source_model', sa.Text(), primary_key=False, nullable=False),
    sa.Column('source_color', sa.Text(), primary_key=False, nullable=False),
    sa.Column('source_type', sa.Text(), primary_key=False, nullable=False),
    sa.Column('source_image_path', sa.Text(), primary_key=False, nullable=False),
    sa.Column('local_image_path', sa.Text(), primary_key=False, nullable=True),
    sa.Column('image_width', sa.Integer(), primary_key=False, nullable=True),
    sa.Column('image_height', sa.Integer(), primary_key=False, nullable=True),
    sa.Column('vehicle_bbox', sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), primary_key=False, nullable=True),
    sa.Column('prediction', sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), primary_key=False, nullable=True),
    sa.Column('comparison', sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), primary_key=False, nullable=True),
    sa.Column('model_version', sa.Text(), primary_key=False, nullable=True),
    sa.Column('status', sa.Text(), primary_key=False, nullable=False, index=True),
    sa.Column('attempt_count', sa.Integer(), primary_key=False, nullable=False),
    sa.Column('last_error', sa.Text(), primary_key=False, nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), primary_key=False, nullable=True),
    sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')"),
)

sa.Table('recognition_sessions', metadata,
    sa.Column('session_id', sa.String(length=64), primary_key=True, nullable=False),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=False, nullable=False, index=True),
    sa.Column('created_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
)

sa.Table('sessions', metadata,
    sa.Column('token_hash', sa.String(length=64), primary_key=True, nullable=False),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=False, nullable=False, index=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), primary_key=False, nullable=False, index=True),
    sa.Column('created_at', sa.DateTime(timezone=True), primary_key=False, nullable=False),
)


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing = set(inspector.get_table_names())
    # Validate all existing tables before any adoption. Do not stamp unknown schemas.
    for table in metadata.sorted_tables:
        if table.name not in existing:
            continue
        columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        for column in table.columns:
            found = columns.get(column.name)
            if found is None or found["nullable"] != column.nullable or not column.type._compare_type_affinity(found["type"]):
                raise RuntimeError(f"Legacy schema differs at {table.name}.{column.name}; migrate explicitly before retrying.")
        primary = set(inspector.get_pk_constraint(table.name)["constrained_columns"])
        if primary != {c.name for c in table.primary_key.columns}:
            raise RuntimeError(f"Legacy primary key differs: {table.name}")
        unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(table.name)}
        unique.update(tuple(i["column_names"]) for i in inspector.get_indexes(table.name) if i["unique"])
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint) and tuple(c.name for c in constraint.columns) not in unique:
                raise RuntimeError(f"Legacy unique constraint missing: {table.name}")
    for table in metadata.sorted_tables:
        table.create(connection, checkfirst=True)
        for index in table.indexes:
            index.create(connection, checkfirst=True)


def downgrade():
    # Adoption cannot distinguish pre-existing user tables from freshly created ones.
    raise RuntimeError("Baseline downgrade is intentionally unsupported; restore a database backup instead.")
