# Database migrations

The backend now uses Alembic instead of runtime `Base.metadata.create_all()`.
API startup, worker startup and `python -m app.commands.init_db` all call
`upgrade_database()`. A PostgreSQL transaction advisory lock serializes upgrades
across containers. Migration failures abort startup rather than continuing with
an incompatible schema. No production database is changed merely by editing code.

## Existing installations

- `0001_baseline` contains a frozen snapshot of the original six tables. It checks
  existing table columns, primary keys and unique constraints, creates missing
  tables/indexes, and adopts compatible pre-Alembic installations without deleting
  rows. An incompatible existing schema produces an error; do not bypass it with
  `alembic stamp head`.
- `0002_seatbelt_result` adds the nullable JSONB seatbelt column if missing and
  preserves it, including its data, if already present.
- Applied versions are recorded in `alembic_version`.

Run with DB_USER, DB_PASSWORD, DB_HOST, DB_PORT and DB_NAME supplied to the process:

```sh
cd backend
python -m app.commands.migrate
# Or:
alembic upgrade head
alembic current
```

Only database environment settings are required for migration commands. API keys,
CORS settings and model services are not required. Shell execution does not load
.env automatically; Compose supplies it using env_file.

For Docker, build the new backend image and optionally run migrations before
restarting the long-running services:

```sh
docker compose build backend worker
docker compose run --rm --no-deps backend python -m app.commands.migrate
docker compose up -d backend worker
```

The PostgreSQL service must already be running for the explicit migration command.
The same upgrade also runs automatically at API/worker startup.

## Future schema changes

Change the SQLAlchemy models, then generate and review a new revision against a
local development database (never generate migrations against production):

```sh
cd backend
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Commit revision scripts with the model change. Do not import application models
inside a revision: revisions must retain their historical schema. Review generated
operations, data backfills and downgrade behavior before deploying.

The two adoption revisions deliberately reject downgrade because dropping adopted
columns/tables would destroy pre-existing data. Use a verified database backup for
rollback when reverting initial adoption. Test future migrations with both a fresh
database and representative existing data.
