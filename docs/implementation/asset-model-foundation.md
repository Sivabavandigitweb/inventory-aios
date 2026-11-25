# Task 8B — independent asset model foundation

Status: two SQLAlchemy metadata models implemented under conditional approval; no migration, database table, runtime grant or operational asset endpoint was created. This supersedes Task 8A's not-yet-implemented status only for the catalog and receiving-header contracts below. The rest of the [asset design](../database/asset-foundation-design.md) remains proposed. Neither PostgreSQL database was accessed.

## Scope classification

| Design element | Classification | Outcome / reason |
|---|---|---|
| Product catalog identity, existing category FK, descriptive fields, active flag, object-shaped specifications and timestamps | Independent | InventoryProduct implemented as a complete catalog record. No inventory balance or product-unit semantics are implied. |
| Optional SKU storage | Independent storage; uniqueness/normalization require decisions | Nullable varchar(80), nonblank if present, no unique index or automatic normalization. |
| Product unit_code and fractional/integral quantity rules | Business decision | Not added. A unit-less catalog record cannot authorize stock operations. No default such as each, piece or unit is inferred. |
| Receipt arrival header, existing user/location FKs and optional reference/notes | Independent | Receipt implemented as a complete arrival header. It is not a finalized receiving transaction. Received time and receiver must be supplied explicitly; no default assumes the current authenticated actor was the physical receiver. |
| Receipt lines, quantities, supplier/procurement/warranty fields | Business decisions plus future receiving workflow | Entire receipt_lines model deferred. Quantity units/precision/integrality and required/unknown/not-applicable procurement handling are unresolved; adding a line shell would misleadingly imply a usable registration contract. |
| Assets, visible asset number, unit ordinal, serial, condition, status and registration state | Business decisions plus future registration workflow | Entire assets model deferred. Number namespace/normalization, approval timing, serial rules and procurement lineage depend on decisions and receipt_lines. Even the justified UNIQUE(source_receipt_line_id,unit_ordinal) cannot be implemented without that complete table. |
| Inventory lots and received quantity | Business decisions plus receiving enforcement | Entire inventory_lots model deferred. Depends on receipt_lines, quantity semantics and atomic equality/mode checks; no duplicate quantity field without its enforcing workflow. |
| Shared idempotency_requests | Deferred at Task 8B; core implemented offline in Task 8D | See [Task 8D implementation](idempotency-foundation.md). No migration, runner or retention policy exists. |
| Balances, movements, registration events; allocations/returns/repairs/disposals | Future workflow implementation | Deferred. Requires concurrency, stock reconciliation, authority and history/audit decisions. No stock or history placeholders registered in metadata. |

## Implemented contracts

Both models use Base, TimestampMixin, typed SQLAlchemy 2 Mapped attributes, UUID primary keys with uuid.uuid4 and PostgreSQL gen_random_uuid defaults, and named constraints/indexes. created_at and updated_at are timezone-aware, non-null server-default timestamps; updated_at has the existing ORM onupdate behavior. No database timestamp trigger is installed by model definitions.

### public.inventory_products

- id UUID PK; category_id UUID NOT NULL references the existing AssetCategory.id with ON DELETE RESTRICT.
- name varchar(200) NOT NULL and nonblank; sku varchar(80) NULL and nonblank if supplied.
- brand/model varchar(150) NULL; no rule claims these constitute complete asset information under R-02.
- specifications JSONB NOT NULL with independent Python dict default, PostgreSQL '{}'::jsonb default and named object-shape CHECK. It describes product specifications, not supplier/location/employee identities.
- active boolean NOT NULL, application/server default true; common timestamps.
- Index ix_inventory_products_category_active(category_id,active). No SKU uniqueness or duplicate tracking_mode column.
- Relationship category resolves to the existing category mapper. No delete cascade to the master.

### public.receipts

- id UUID PK; received_at timestamptz NOT NULL without an inferred arrival-time default.
- received_by_id UUID NOT NULL references existing User.id; location_id UUID NOT NULL references existing Location.id; both use ON DELETE RESTRICT.
- external_reference varchar(150) NULL and nonblank if supplied; notes text NULL; common timestamps. External reference is not unique and is not a generated receipt number.
- Indexes on received_at, received_by_id and (location_id,received_at).
- Relationships received_by and location resolve to existing mappers, without master delete cascades. No receipt lines, approval state, automatic actor assignment or write API is implied.

Both new tables explicitly use schema public. Existing masters use schema=None in Base.metadata; ForeignKey references their actual mapped columns rather than introducing duplicate public-qualified master Table objects. Consequently bare metadata DDL inherits the legacy master search-path convention for those references. The future migration must explicitly use referent_schema='public' for category/user/location FKs, or a reviewed equivalent schema translation. Offline tests compile both the existing convention and the public-qualified form. No existing table schema or Alembic environment was changed to accommodate this.

## Integrity and workflow boundaries

Named local CHECKs enforce nonblank labels/references and JSON object shape when later installed on PostgreSQL. No CHECK attempts to validate another table. Receipt-unit uniqueness, quantity non-negativity and lifecycle constraints are not silently omitted from implemented stock tables: those whole tables remain deferred. Existing PK/FK/naming conventions and master indexes remain unchanged.

Future registration must lock source lines and relevant category/product records using one reviewed global lock order; forbid mode/category changes that invalidate receipts; serialize count/quantity checks and assign unique receipt-unit keys. Stock operations must atomically lock affected balances, reconcile journal deltas and custody/outflows, and reject over-registration, negative availability and mismatched transfers. Unique idempotency claims and matching fingerprints protect retries; a fresh key does not establish a physically new asset. None of these workflow guarantees is supplied by catalog/header metadata.

Registration provenance records the domain event of receiving/registering a specific asset or lot and its request/source lineage. General audit_events records changes across domains. A future provenance table is justified only if that domain lineage cannot be represented adequately in existing typed relationships; it must not become a second generic audit log. Neither would complete R-11 without approved previous/updated value capture and sensitive-field redaction. Audit trust, permissions and employee-registration policy remain unchanged and pending.

## Future migration preparation

1. After separate migration approval, extend 7d4a9c2e1b60 with the two independent tables. Existing asset_categories, users and locations must precede them. Do not autogenerate or execute against either database during Task 8B.
2. Expected additions for this slice: 2 tables, 2 UUID PK constraints (and their indexes), 3 RESTRICT FKs, 4 named CHECK constraints, 4 explicit secondary indexes, 4 created/updated timestamp columns. PostgreSQL also represents NOT NULL constraints in its catalog; do not compare their count with archive-listed ordinary constraints. No new master, enum, sequence, number generator, stock or audit table is needed.
3. Decide whether to reuse the existing timestamp function with 2 new update triggers; model metadata itself adds no trigger. Review function ownership/search_path/execute behavior, trigger naming and down-migration order. UUID defaults require no numbering sequence.
4. Migrator must explicitly assume inventory_aios_owner using existing security configuration. Ownership/default PUBLIC ACLs and new-object privileges require inspection. No runtime grants accompany this model task. A later command's actual ORM fields, RETURNING and locking queries determine minimal runtime permissions; no ALL privileges or test-driven privilege widening.
5. Future migrations for receipt lines, assets, lots, shared requests and workflow/history must wait for their decisions and enforce cross-table/concurrent invariants. Existing revisions remain unchanged. Review schema-qualified FKs and autogeneration diffs to ensure existing core tables are neither recreated nor dropped.
6. Before any execution: separately authorized read-only target/revision/ownership verification, checksum-verified backup, recovery plan, and disposable-database rehearsal with baseline rows/schema/ACLs. Do not infer authorization to migrate inventory_aios_dev. Refuse destructive downgrade with retained business records; review recovery or forward-fix separately.

## Offline evidence and remaining database tests

Tests register both new tables with the existing Base, resolve all mappers/FKs/relationships, verify UUID/timestamp/JSON defaults, exact structural CHECKs, indexes and nullability, and compile PostgreSQL table/index DDL. A new-test fixture rejects both SQLAlchemy Engine.connect and psycopg.connect calls. It does not create a database or use SQLite as proof of PostgreSQL behavior. The existing metadata allowlist was expanded by exactly these two public-qualified table keys; previous core assertions remain active.

Validation: 94 non-integration tests passed; 41 integration tests deselected. Ruff, Python compilation and git diff --check are required final checks. The pre-existing Starlette/httpx deprecation warning remains unrelated. Offline success does not prove PostgreSQL constraint, trigger, isolation or privilege enforcement.

Future approved PostgreSQL tests must verify FK rejection/deletion restrictions, JSON/nonblank CHECK SQLSTATEs, server defaults, timestamp triggers, actual ORM read/write behavior, migration ownership/ACLs, and absence of unintended PUBLIC/runtime grants. Later stock/registration slices require parallel-connection race, rollback, idempotent replay, quantity and source-line consistency tests. Preserve the existing integration suites without executing them in Task 8B.

## Next decision/task

Review quantity units and precision, procurement completeness, receiver identity semantics, visible-number namespace and registration approval timing. Then approve the receipt-line contract or separately approve preparation of a migration for only the two completed independent models. Operational APIs, audit grants, identity-provider configuration and employee registration remain disabled or pending as before. R-11 remains partially implemented.
