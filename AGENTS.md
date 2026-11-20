# Inventory AIOS — Codex Project Instructions

## Project overview

Inventory AIOS is an inventory management system with a React and TypeScript frontend and a FastAPI and Python backend.

## Working guidelines

- Keep frontend and backend responsibilities clearly separated.
- Use TypeScript for frontend code and Python for backend code.
- Keep configuration and secrets in environment files; never commit credentials.
- Document requirements, architecture, database decisions, and implementation notes in the matching `docs/` subdirectory.
- Use PostgreSQL with SQLAlchemy and Alembic for persistence and migrations.
- Treat external API integrations, including the Grok API, as explicitly configured services.
- Add tests and update relevant documentation as application features are implemented.
- Do not install dependencies, connect to external services, or make database changes unless explicitly requested.

## Repository hygiene

- Review existing files before editing them.
- Keep generated files, local environments, caches, and secrets out of version control.
- Do not commit or push changes unless explicitly requested.
