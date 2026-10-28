"""Add seatbelt storage if absent; preserve existing legacy and versioned results."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_seatbelt_result"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns("vehicle_recognitions")}
    existing = columns.get("seatbelt_result")
    if existing is None:
        op.add_column("vehicle_recognitions", sa.Column(
            "seatbelt_result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True))
    elif not isinstance(existing["type"], sa.JSON) or not existing["nullable"]:
        raise RuntimeError("Existing seatbelt_result column must be nullable JSON/JSONB.")


def downgrade():
    raise RuntimeError("Seatbelt storage may contain legacy data; destructive downgrade is unsupported.")
