# Asset database foundation — Task 8A review draft

## Task 8D shared idempotency status

The shared `IdempotencyRequest` SQLAlchemy metadata, canonical fingerprint utility and pure replay decision are implemented offline. The [Task 8D implementation note](../implementation/idempotency-foundation.md) is authoritative for the current fields and deferred runner. Earlier idempotency columns below that mention response bodies, error caches or expiry are superseded proposals; no cleanup duration or database behavior was approved. No migration, live command runner or database access occurred in Task 8D.

## Task 8B implementation status

Conditional approval has produced only the independent InventoryProduct catalog and Receipt header models. Receipt lines, assets, lots, idempotency and workflow tables remain deferred; unit, numbering and other business rules are not approved. No migration or database change occurred. See [implemented/deferred scope](../implementation/asset-model-foundation.md) for the exact model contracts and limitations. The detailed Task 8A design below remains a proposal wherever not explicitly implemented.

Status: proposed schema, not approved for implementation. No models, migrations, database access or operational writes are part of Task 8A. All names, sizes, constraints and workflow mechanics below are technical proposals unless marked confirmed. This detailed asset design refines the conceptual rows in [schema-plan.md](schema-plan.md); unrelated domain plans remain unchanged.

## Source evidence and boundaries

The original six-page [requirements PDF](../requirements/Inventory%20%26%20Asset%20Management%20Automation%20System.pdf) was read locally. Requirement identifiers follow the [matrix](../requirements/requirements-matrix.md).

| Source | Confirmed requirement | Design response / unresolved interpretation |
|---|---|---|
| R-01, section 1 | Register newly purchased/received assets immediately on arrival. Categories include desktops, laptops, monitors, accessories, furniture, CCTV, pen drives, external disks, networking, printers, UPS, mobile devices and other company assets. | Reuse category masters; receipts capture arrival. Do not infer a fixed exhaustive category list or seed codes. |
| R-02, section 2 | Auto-generated Asset ID; category, brand, model, serial, specifications, purchase date, supplier, warranty, cost; Available/Allocated/Repair/Damaged/Disposed status. | Internal UUID plus proposed visible asset number. Required information does not establish handling of unknown/not-applicable values or serial uniqueness scope. |
| R-03, section 3 | Received date, receiver, quantity, location, technical specifications; optional supporting documents. | Receipt headers/lines and optional attachment metadata. Quantity receiving is explicit; pooled/non-serialized accounting is a requested technical design, not an explicit PDF classification rule. |
| R-04–R-05, sections 4–5 | Assign to employee; retain employee ID/name, department/team/designation, allocation date, assigner and condition; link employee profile. | Reuse employee/user/org IDs; future allocations hold historical assignment context. No duplicate employee master. |
| R-06, section 6 | Reflect team/department/promotion changes while retaining history. | Current employee context comes from existing masters; historical assignment context must not be overwritten. |
| R-07–R-08, sections 7–8 | Identify assigned assets and return before exit completion; retain return date, returner, verifier, condition, remarks and history. | Future allocations/returns support custody history and partial quantity returns. Return verification remains distinct from physical receipt. |
| R-09, section 9 | Report/repair dates and actors, cost, service provider, current status. | Future repair records reference assets; reuse suppliers only if service-provider classification is approved. |
| R-10, section 10 | Approval workflows for registration, allocation, return, disposal. | Authority, steps, self-approval and registration-versus-approval timing are unresolved. No approved chain is inferred. |
| R-11, section 11 | User, time, previous and updated values; history for audit/management review. | Current audit envelope is partial. Asset history cannot be claimed complete without approved value capture/redaction. |
| R-12–R-15, sections 12–15 | Pending registration/returns/approvals and missing-information reminders; warranty alerts; status totals; Asset ID/employee/org/serial search; inventory and history reports. | Indexed relations and immutable procurement/history support later queries. Dashboard counting of units versus lots requires definitions. |
| R-16–R-17, sections 16–17 | Mobile entry and authorized device access; preferred QR/barcode, RBAC and exports. | Stable IDs and idempotent commands; barcode is a possible representation of an identifier, not a confirmed numbering format. |

No LED prefix, digit width, starting number, yearly reset or location-specific scheme appears in the PDF or reviewed Markdown. The existing matrix explicitly leaves numbering format, prefix, scope and immutability undecided. Manual Google Sheets are mentioned, but no source asset register was provided or inspected.

## Existing foundation to reuse

Repository inspection: `core.py` already defines `asset_categories(id,code,name,tracking_mode,active)`, `suppliers`, hierarchical `locations`, `employees`, `users`, departments/teams/designations, roles and employee history. Category tracking mode is constrained to `individual` or `quantity`; it is not per product today. Category/location codes are unique; supplier names have a non-unique search index. Do not create alternative masters or treat supplier-name equality as identity.

Existing revisions are `36368303c6c6` (core, UUID/timestamp/history safeguards) followed by `7d4a9c2e1b60` (audit table, validator and immutability triggers). The user-reported rehearsal is at the latter revision; Task 8A does not recheck any database. The [audit permission readiness](../implementation/audit-permission-readiness.md) remains pending approval. Authentication and audit trust policies are unchanged.

## Common mapping conventions

Unless explicitly nullable (`?`), columns below are NOT NULL. New entity PKs are `id uuid`, with existing-style Python UUID defaults and PostgreSQL `gen_random_uuid()` defaults. Mutable records have `created_at, updated_at timestamptz` with server timestamps and a reviewed database update trigger. Immutable events have `recorded_at timestamptz DEFAULT now()` and no mutable timestamp. Business `received_at/effective_at` are distinct from server recording time. Foreign keys default to `ON DELETE RESTRICT`; do not cascade-delete inventory or history. Every referenced FK needs a supporting lookup index unless covered by a leading composite key. No JSON object substitutes for employee, supplier, category, location or relational workflow references.

## Proposed table contracts

### inventory_products

`id uuid PK`, `category_id uuid FK asset_categories`, `sku varchar(80)?`, `name varchar(200)`, `brand varchar(150)?`, `model varchar(150)?`, `specifications jsonb DEFAULT '{}'`, `unit_code varchar(30)`, `active boolean DEFAULT true`, common timestamps.

CHECK nonblank name/unit; CHECK JSON object; optional SKU must be nonblank. Proposed partial UNIQUE(sku) when non-null only after SKU scope/normalization is approved. A product describes common attributes; it does not own procurement facts or stock balances. Tracking mode is derived from its category, avoiding a second independently editable mode. Proposed rule: freeze category tracking mode and product/category association after first receipt until an explicit reclassification workflow exists. Enforce with reviewed database triggers that lock referenced product/category rows; a CHECK cannot enforce cross-table mode consistency.

### receipts

`id uuid PK`, `received_at timestamptz`, `received_by_id uuid FK users`, `location_id uuid FK locations`, `external_reference varchar(150)?`, `notes text?`, common timestamps. No invented human receipt-number sequence. CHECK optional external_reference is nonblank. External references are not globally unique: different suppliers may reuse them. Receiver identity semantics (physical receiver versus authenticated recorder) need confirmation; authenticated actor is always independently recorded in history/audit.

### receipt_lines

`id uuid PK`, `receipt_id uuid FK receipts`, `line_number integer`, `product_id uuid FK inventory_products`, `quantity_received numeric(18,3)`, `supplier_id uuid FK suppliers?`, `purchase_date date?`, `unit_cost numeric(19,4)?`, `currency_code varchar(3)?`, `warranty_start date?`, `warranty_end date?`, `warranty_terms text?`, `received_specifications jsonb DEFAULT '{}'`, common timestamps.

UNIQUE(receipt_id,line_number); CHECK line_number > 0, quantity_received > 0, unit_cost IS NULL OR unit_cost >= 0; cost and currency are both absent or both present; currency is three uppercase letters (valid currency set still requires business confirmation); CHECK warranty_end >= warranty_start when both present; CHECK specifications is an object. No assumed currency, taxes, valuation method, warranty length or warranty reference date. Snapshot technical/procurement facts here so later product-master edits do not rewrite purchase history. A different supplier, cost or warranty requires a separate line. Null procurement fields represent unknown/not applicable only under an approved completeness policy; do not silently fill with zero or fabricated dates.

### assets (one physical tracked unit)

`id uuid PK`, `asset_number varchar(100)`, `source_receipt_line_id uuid FK receipt_lines`, `unit_ordinal integer`, `serial_number varchar(200)?`, `unit_specifications jsonb DEFAULT '{}'`, `current_location_id uuid FK locations`, `condition_description text?`, `lifecycle_status varchar(20)`, `registration_state varchar(20)`, `version bigint DEFAULT 1`, common timestamps.

UNIQUE(source_receipt_line_id,unit_ordinal); CHECK ordinal > 0 and version > 0; nonblank asset_number and optional serial; CHECK unit specifications is an object. Proposed global UNIQUE(asset_number), conditional on approval of numbering scope; see numbering section for the location-scoped alternative. Do not impose global serial uniqueness without approval: initially a non-unique serial index plus duplicate review; any later uniqueness key must follow agreed manufacturer/product scope and normalization. No duplicate product/category/supplier/purchase fields: join the immutable source line and its product/category. Unit-specific differences use their own source line or explicitly recorded unit specifications. Cost is per unit, inherited from the source line, not copied and edited in two places.

The five lifecycle values are the PDF's `available`, `allocated`, `repair`, `damaged`, `disposed`. Proposed registration states `pending`, `approved`, `rejected` are a separate axis awaiting R-10 workflow review. No default approved state. A pending/rejected record cannot be allocated even if physically available. Receipt capture remains immediate; whether pending asset registration records satisfy R-01 needs management confirmation. No `current_employee_id` cache: active allocation is the custody source. Ownership is company ownership in the source scope; borrowing, multiple legal owners and ownership transfers are not specified.

### inventory_lots (quantity provenance)

`id uuid PK`, `source_receipt_line_id uuid FK receipt_lines UNIQUE`, `received_quantity numeric(18,3)`, common timestamps. CHECK received_quantity > 0. Proposed one lot per quantity receipt line; create multiple lines for distinct procurement/condition batches. Lot retains procurement identity as stock moves between locations. Do not place a single mutable location or duplicate product/supplier information on the lot.

A reviewed cross-table constraint trigger locks the source line, checks quantity category mode, and enforces received_quantity = quantity_received. Individual lines may create assets only; quantity lines may create lots only. Locking the same source line prevents concurrent mixed registration and over-registration. Changes to finalized source quantities require an explicit correction workflow, never a silent overwrite.

### inventory_balances (stock by location and availability bucket)

`id uuid PK`, `lot_id uuid FK inventory_lots`, `location_id uuid FK locations`, `bucket varchar(20)`, `quantity numeric(18,3) DEFAULT 0`, `quantity_reserved numeric(18,3) DEFAULT 0`, `version bigint DEFAULT 1`, common timestamps.

UNIQUE(lot_id,location_id,bucket); CHECK quantity >= 0, reserved >= 0, reserved <= quantity, version > 0. Proposed buckets `available`, `pending_return`, `repair`, `damaged` describe stock physically held at a company location; all except available require reserved = 0. These buckets are proposals, not new individual-asset states. Allocated units are outside location-held balance and are accounted for by future allocation custody balances. Disposed quantity is an irreversible outflow subject to approved corrections. `available_to_allocate = available.quantity - available.quantity_reserved`; do not subtract reservations twice from total stock.

Decimal quantity is a proposed technical capacity, not approval for fractional laptops or consumables. Unit/precision and indivisible categories require confirmation; individual lines must be integral and asset count must match their received quantity before registration finalization. Discrete quantity products will require an approved integral-quantity constraint/trigger as well.

### inventory_movements (append-only stock journal)

`id uuid PK`, `operation_id uuid FK idempotency_requests`, `entry_number integer`, `lot_id uuid FK inventory_lots`, `balance_id uuid FK inventory_balances`, `quantity_delta numeric(18,3)`, `reserved_delta numeric(18,3) DEFAULT 0`, `movement_kind varchar(30)`, `actor_user_id uuid FK users`, `effective_at timestamptz`, `recorded_at timestamptz DEFAULT now()`, `reason text?`.

UNIQUE(operation_id,entry_number); CHECK entry_number > 0; at least one delta is nonzero. Proposed kinds `receive`, `reserve`, `release`, `allocate`, `return`, `transfer`, `reclassify`, `dispose`, `correction`; only receiving would be enabled in the first service slice. Composite FK (balance_id,lot_id) references an explicit UNIQUE(id,lot_id) on inventory_balances to prevent wrong-lot entries. Future typed allocation/return/disposal FKs are added with their workflows; operation_id is not a substitute for those FKs.

Proposed enforcement: INSERT-only journal and a reviewed SECURITY INVOKER trigger that locks the balance, applies deltas, and checks invariants. Runtime must not freely update balances: a balance UPDATE guard requires nested execution from that trigger (and denied TRIGGER/DDL privileges), with a reviewed transaction-final reconciliation check verifying sum(journal deltas) = balance. This is a design candidate requiring proof against direct-SQL bypass; it is not a new SECURITY DEFINER design or an approved privilege change. If enforcement cannot be demonstrated, defer stock writes rather than grant broad balance UPDATE. Transfer/reclassification pairs must sum to zero per lot and operation; receiving equals its source line; later allocation outflows equal new custody quantities and return inflows equal verified custody reductions. CHECKs alone cannot enforce these aggregate/cross-table rules; deferred constraint triggers and service tests must cover them.

### asset_registration_events (append-only provenance)

`id uuid PK`, `asset_id uuid FK assets?`, `lot_id uuid FK inventory_lots?`, `operation_id uuid FK idempotency_requests`, `event_kind varchar(30)`, `actor_user_id uuid FK users`, `effective_at timestamptz`, `recorded_at timestamptz DEFAULT now()`, `reason text?`.

CHECK exactly one of asset_id/lot_id is non-null. Proposed kinds `registered`, `imported`, `correction`; unique initial registration per target using separate partial UNIQUE(asset_id) / UNIQUE(lot_id) for initial kinds. UNIQUE(operation_id,asset_id) and UNIQUE(operation_id,lot_id) prevent replayed event inserts. This records who registered an item, when and via which request. It supplements audit_events; it is not a second complete R-11 audit system. Corrections append events, never delete original records; before/after value storage awaits the approved R-11 redaction design. Deny UPDATE/DELETE/TRUNCATE and install reviewed protection triggers.

### idempotency_requests (reuse the existing proposed contract)

This table is planned but not implemented. Do not create a parallel asset-specific request table. Proposed columns: `id uuid PK`, `principal_id uuid FK users`, `operation_scope varchar(200)`, `idempotency_key varchar(200)`, `request_fingerprint varchar(64)`, `status varchar(20)`, `response_status smallint?`, `response_body jsonb?`, `resource_type varchar(80)?`, `resource_id uuid?`, `completed_at timestamptz?`, `expires_at timestamptz?`, `error_code varchar(100)?`, common timestamps. UNIQUE(principal_id,operation_scope,idempotency_key); nonblank scope/key; 64 lowercase hex SHA256 fingerprint; proposed states processing/succeeded/failed and response status 100–599 if present. Expiry may remain NULL until retention is decided. Do not auto-delete keys referenced by inventory/history. Response must contain only authorized, minimal replay data, not secrets or sensitive audit values.

## Relationships and future extensions

Category -> products -> receipt lines -> either individual assets or a quantity lot. Receipts link receiver and location; lines link supplier. Lots -> balances -> movements, with durable source-line procurement references. Registration events reference an asset or lot and an idempotent command. All actors reference users. Locations reuse the existing hierarchy; prevent new cycles in a separately reviewed master-data validation change.

Future allocations reference employees and exactly one asset or lot; asset quantity = 1, lot quantity > 0. Enforce one active allocation per individual asset with a partial UNIQUE index, not only a prior SELECT. Quantity allocations retain assigned/verified-returned/disposed-or-other-approved-resolution quantities without reusing lot balances as employee custody. Returns can be multiple per quantity allocation; do not enforce the old broad concept of one return per allocation. Each return requires recorded actors, condition and verification before becoming available. Transfers change locations through paired journal entries for lots or an asset location-history event; employee org transfers use existing employee_history. Historical employee context references immutable org-history events or approved explicit snapshots, not current-name joins alone. Repairs/disposals and approval rows remain future typed relationships; no generic unvalidated workflow FK is implemented now.

Optional receiving attachments use a later receipts-document association with private document metadata; provider/size/retention/access policies are undecided. No blob content or external URLs are required in the foundation tables.

## Numbering and import decisions

Separate the internal UUID (automatically generated now in the proposed model) from the visible asset_number. No LED regex, sequence name, prefix, start, reset or padding is specified or seeded. Propose immutable globally unique visible numbers because search, labels and transfers need stable identity; management must explicitly accept that scope. If numbering is location-specific, use immutable issuing_location_id plus UNIQUE(issuing_location_id,asset_number); the current physical location must never be the uniqueness scope. APIs/labels must then carry the issuing scope to resolve ambiguity.

Once rules are approved, use PostgreSQL nextval for a global monotonic scheme or an atomic per-scope counter row for scoped numbering; never SELECT MAX + 1. Unique constraints remain the final concurrent collision barrier. Sequences can have gaps on rollback; gapless/legal requirements are undecided and require a separate design. No counter, sequence or runtime sequence grant is created in Task 8A.

Before importing Google Sheets, preserve source rows and original labels, identify duplicates/case/spacing collisions and missing IDs, and obtain management's mapping/renumbering decision. Proposed later import provenance: source_system, source_record_key with a unique pair, batch identifier and original_asset_number; do not assume asset_number or a serial deduplicates all physical duplicates. Reserve/import existing labels before generating any new numbers; establish a high-water mark only after reviewing actual approved data and namespace. Existing disposed labels must not be silently reused. A fresh idempotency key does not prove a newly received physical asset is new; source receipt/unit keys and approved serial/import controls remain necessary.

## Index plan

Unique constraints provide their own indexes. Additional proposed indexes: products(category_id,active); receipts(received_at), (received_by_id), (location_id,received_at); receipt_lines(product_id), (supplier_id,purchase_date), (warranty_end) when present; assets(current_location_id,lifecycle_status), (lifecycle_status,registration_state), (serial_number) when present; lots(source_receipt_line_id) covered by UNIQUE; balances(location_id,bucket) and their unique lot/location/bucket key; movements(lot_id,effective_at,id), (balance_id,recorded_at,id), (actor_user_id), unique operation/entry; registration events(asset_id,recorded_at,id), (lot_id,recorded_at,id), (actor_user_id); idempotency(expires_at) when present. Add remaining FK indexes where not covered. Category filtering joins products/source lines; do not add an index on nonexistent assets.category_id. Warranty queries join source lines; no GIN/trigram extension until actual workload and permission review justify it.

## Transactions and lifecycle safeguards

Registration claims the idempotency key and locks receipt lines in UUID order, then products/categories as required by the agreed global lock order, generates unique identifiers, creates assets or the lot, writes initial journal/provenance/audit records, stores the replay response and commits one transaction. All workflows must use the same lock order; category reassignment and receiving must not invert it. Define the final order before implementation. Unfinished receipt lines may be partial; finalization verifies exact counts/integral individual quantities. Database triggers serialize source-line registration and deny total over-registration. Request replay with changed payload is 409; a matching concurrent request waits boundedly for the unique-key owner, then replays only after authorization is rechecked. Transient failures roll back the claim and all business effects; post-commit response loss replays the stored result. No independently committed processing row or permanent-failure handling is introduced without tests for crashes and transaction boundaries.

Quantity reconciliation must satisfy received quantity plus approved net corrections = company-location balances plus outstanding employee custody plus approved disposed/other explicitly authorized outflows, per lot. Reservations are subsets of location balances, not an extra ownership bucket. In the initial receiving-only slice, company-location balances equal received quantity; later workflows must extend the reconciliation constraint before being enabled. No loss/consumption outflow or opening-stock adjustment is implicitly approved.

For stock, lock source/destination balances in deterministic ID order, check available quantity including reservations, insert journal entries and update projections in the same transaction. Deferred reconciliation rejects mismatched movement pairs and inconsistent balances. Deadlock/serialization retries must be bounded and retain the idempotency key. Proposed asset transitions are available -> allocated -> available (verified return), available/allocated -> damaged -> repair -> available, and approved disposal -> disposed. Allowed transitions for damaged allocations, disposal while assigned, lost items and reversal of disposal remain unresolved; do not enable them by guessing. A valid status CHECK is not a transition validator. Recheck current version/state and approval inside the locked transaction.

See the [implementation plan](../implementation/asset-foundation-plan.md) for permissions, API, migration and testing gates.
