---
name: database-management
description: Design and maintain the Inventory AIOS PostgreSQL, SQLAlchemy 2, and Alembic data layer safely.
---

# Database management

Use this skill for Inventory AIOS schema, persistence, migration, and data-safety work.

- Use PostgreSQL with SQLAlchemy 2 and Alembic; model relationships, constraints, indexes, and transaction boundaries deliberately.
- Preserve asset and employee history needed for allocation, transfer, return, repair, disposal, and auditability.
- Use migrations that are reviewable, reversible where practical, and safe for existing data; document backup and rollback requirements for risky changes.
- Prevent invalid states with database constraints and service-level validation rather than relying on UI behavior.
- Require read-only inspection before destructive data operations and explicit approval before any production connection or production mutation.
- Do not infer retention, deletion, backup, or privacy policy where company decisions are missing; record those as unresolved decisions.
