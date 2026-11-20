# Inventory AIOS Backend

FastAPI foundation for Inventory AIOS. This phase provides a versioned API shell, health endpoint, environment configuration, CORS for the local frontend, structured request logging, centralized error responses, and test scaffolding.

Inventory CRUD, authentication, PostgreSQL, Alembic, Grok, and production integrations are intentionally not implemented in this foundation.

## Requirements

- Python 3.12 or another supported Python version
- A local virtual environment

## Setup

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

The application has safe development defaults. The `.env` file is local-only and must never be committed.

## Run locally

```powershell
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation is available at `/docs`.

Health check:

```text
GET http://127.0.0.1:8000/api/v1/health
```

## Validation

```powershell
ruff check .
pytest
python -c "from app.main import app; print(app.title)"
```

The local frontend origin `http://localhost:5173` is allowed by CORS. No database or external service is required to run this foundation.

## PostgreSQL development setup (Windows)

Use a dedicated local database named `inventory_aios_dev`. Do not point this project at Management AIOS, company production, or any shared company database.

1. Install PostgreSQL locally using the official Windows installer. Include the PostgreSQL server and command-line tools. pgAdmin is optional.
2. Open SQL Shell (`psql`) or pgAdmin and create a development role and database. Replace the placeholder password locally:

```sql
CREATE USER inventory_aios WITH PASSWORD '<replace-with-a-local-password>';
CREATE DATABASE inventory_aios_dev OWNER inventory_aios;
```

3. Copy the environment template and set the local URL:

```powershell
Copy-Item .env.example .env
```

Set `INVENTORY_DATABASE_URL` in `.env` to a local value such as:

```text
postgresql+psycopg://inventory_aios:<local-password>@localhost:5432/inventory_aios_dev
```

Never commit `.env`, print the URL, or paste credentials into source files or logs.

## Database health check

The application health endpoint does not contact PostgreSQL. The separate database check is:

```text
GET /api/v1/health/database
```

It returns `not_configured` when no URL is provided and `unavailable` for a safe connection failure. This task did not test a real PostgreSQL connection.

## Alembic foundation

Alembic is initialized for future migrations, but no inventory models or revisions exist yet. Configure the local development URL in `.env` before using commands that connect to the database:

```powershell
alembic -c alembic.ini current
alembic -c alembic.ini upgrade head
```

Future migration generation, after approved SQLAlchemy models exist, will use:

```powershell
alembic -c alembic.ini revision --autogenerate -m "describe approved schema change"
```

Review generated migrations and take a verified backup before applying them. Do not run migrations against production without explicit approval. No Alembic command requiring a database connection was executed for this task.