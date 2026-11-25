# Asset business decisions — Task 8C

Status: recommendations for management review. **Every decision below is pending; none is approved.** Existing InventoryProduct and Receipt models remain unchanged. Answer by decision ID with the selected option and any required details; approval must identify the approver and date. No database access or operational writes are authorized by this document.

## Already settled by the original requirements — no reconfirmation requested

The [original requirements PDF](Inventory%20%26%20Asset%20Management%20Automation%20System.pdf) requires immediate registration on arrival (R-01); auto-generated Asset ID and category/brand/model/serial/specifications/purchase date/supplier/warranty/cost (R-02); received date, receiver, quantity, location and specifications, with optional documents (R-03). The lifecycle statuses are Available, Allocated, Repair, Damaged and Disposed (R-02). Allocation/return condition and accountable people, employee links and retained history are required (R-04–R-09). Registration/allocation/return/disposal approvals are required (R-10). R-11 requires actor, time, previous and updated values. Missing-information reminders are expressly contemplated (R-12). Assigned assets must be returned before employee exit completes (R-07); this review proposes no exception.

The PDF does **not** define LED numbering, quantity units, approval authority or the policies below. A quantity on a delivery does not itself mean those items should be pooled rather than individually tracked. Details and implementation recommendations are in the [receiving contract](../database/asset-receiving-contract.md).

## Decisions needed for receipt lines and receiving

### ABD-01 — Which items need their own tracking label?

**Question:** Which categories must be tracked item by item, and which may be counted together?

- **Source:** R-01–R-04, R-07, R-14.
- **Options:** individual tracking for all; a category-by-category individual/pooled list; mixed tracking within a category.
- **Recommend:** approve a category list, retaining individual tracking where serial, custody, warranty or condition must be traced per item. Use pooling only for items genuinely interchangeable for those purposes.
- **Reason:** preserves accountability and fits the existing category-level tracking method. Mixed categories require an explicitly reviewed model change.
- **Affected / blocking:** products, receipt_lines, assets, inventory_lots; blocks their tracking validation, not existing catalog/header models.
- **Approval:** Pending; approved category list required.

### ABD-02 — How is each item counted or measured?

**Question:** Which units do staff use, and may a quantity contain a fraction?

- **Source:** R-03 quantity; R-04/R-08 allocation and return.
- **Options:** whole-item counts only; units and decimal precision defined per product; packages with automatic unit conversion.
- **Recommend:** whole counts for individual items; approve the unit and permitted precision for each pooled product. Defer automatic box/pack conversion until conversion rules are agreed.
- **Reason:** prevents fractional physical assets and incorrect totals across incompatible units. No unit list or decimal precision is presumed approved.
- **Affected / blocking:** receipt_lines, product unit metadata, lots, balances and movements; blocks quantity columns/checks and stock operations.
- **Approval:** Pending; unit/precision list required.

### ABD-03 — Who receives goods, and who may record them?

**Question:** Must the person receiving goods have a system account, or may an authorized colleague record the receipt for them, and at which locations?

- **Source:** R-03 received by/location; R-16 entry access.
- **Options:** receiver records personally; an authorized clerk records for another registered user; receiving personnel may include people without system accounts.
- **Recommend:** allow an authorized clerk to record for another registered receiver, with the physical receiver and authenticated recorder kept distinct and permitted locations assigned explicitly.
- **Reason:** avoids falsely attributing physical receipt to the clerk. Non-account receivers would need a reviewed employee/person reference, not a fabricated user.
- **Affected / blocking:** Receipt.received_by_id and future authorization/provenance; blocks receiving activation. The current users FK remains unchanged until a decision is approved.
- **Approval:** Pending; responsible staff and location scope required. This does not select an authentication provider.

### ABD-04 — What happens when purchase or warranty facts are missing?

**Question:** How should staff handle received or historical items whose supplier, purchase date/cost, serial or warranty details cannot yet be established?

- **Source:** R-01 immediate registration; R-02 information capture; R-12 missing-information reminders.
- **Options:** block all entry until complete; record arrival and flag unknown/not-applicable facts for completion; allow blanks without follow-up.
- **Recommend:** record arrival immediately, distinguish unknown from genuinely not applicable with a reason, and assign a responsible person for completion. Do not invent dates, costs, serials or warranty coverage. Management must specify which gaps block allocation and who accepts historical exceptions.
- **Reason:** meets arrival visibility while retaining the required information obligation. Missing information is not automatically a zero value or a waived requirement.
- **Affected / blocking:** receipt_lines, assets and imports; blocks procurement nullability/completeness and release rules.
- **Approval:** Pending; field applicability and exception/completion responsibilities required.

### ABD-05 — Which purchase amount and currency should staff record?

**Question:** Should unit cost include tax, delivery charges and discounts, and which currencies are allowed?

- **Source:** R-02 purchase cost/date/supplier; R-15 purchase history.
- **Options:** invoiced unit price with a defined tax treatment; landed unit cost including allocated charges; both as separate values. Currency can be one company currency or the original transaction currency.
- **Recommend:** retain original transaction currency and invoiced unit price, with finance defining tax/discount treatment; defer landed-cost allocation and currency conversion unless required. Keep purchase date distinct from arrival date and retain the supplier invoice/order reference when available.
- **Reason:** avoids silently converting financial history or treating receipt date as purchase date. The PDF specifies neither a currency nor a valuation method.
- **Affected / blocking:** receipt_lines cost/currency/purchase-reference fields and financial reports; blocks their final contract.
- **Approval:** Pending; finance input required, including treatment of free/replacement items and unavailable references.

### ABD-06 — How should short, extra or damaged deliveries be handled?

**Question:** Who decides whether a short, extra or damaged delivery is accepted, and whether a missing quantity is still expected?

- **Source:** R-01/R-03 receiving, R-09 damage, R-10 approval.
- **Options:** record actual arrivals with authorized discrepancy review; only accept exactly matching deliveries; use an explicitly approved tolerance policy.
- **Recommend:** record each actual arrival separately, link its purchase reference, and flag discrepancies for a named reviewer. Do not treat an order's full quantity as received or invent an acceptance tolerance.
- **Reason:** preserves physical stock accuracy and supports partial deliveries without duplicate receipt records. Purchasing/order fulfillment is a later workflow if needed.
- **Affected / blocking:** receipt_lines and receiving/discrepancy workflow; blocks acceptance/finalization, not header capture. Basic arrival-line metadata can proceed once ABD-02/04/05 are settled.
- **Approval:** Pending; reviewer and acceptance authority required.

## Decisions needed for individual assets and pooled stock

### ABD-07 — What should the visible asset number mean?

**Question:** Must asset numbers be unique across the whole company or only within their issuing location, and what exact LED format should new labels use?

- **Source:** R-02 generated Asset ID; R-14 search; R-17 preferred barcode/QR tracking.
- **Options:** company-wide immutable number; issuing-location number plus a permanent location identifier; retain legacy labels and introduce a separately approved new namespace.
- **Recommend:** company-wide immutable visible numbers, preserving valid existing labels where possible. Request the actual approved LED specification and a source register before selecting a format or counter. Transfers should not renumber assets. Confirm whether unused gaps are acceptable.
- **Reason:** unambiguous search and stable history. Neither the PDF nor reviewed project documentation supplies a prefix format, sequence, start or reset rule.
- **Affected / blocking:** assets.asset_number, uniqueness constraint, imports and future number generation; blocks the asset model contract. Internal UUIDs need no management numbering decision.
- **Approval:** Pending; no LED format or starting number proposed or approved.

### ABD-08 — How should duplicate serial numbers and catalogue codes be handled?

**Question:** Are supplier serial numbers and catalogue codes reliable enough to reject duplicates automatically?

- **Source:** R-02 serial capture; R-14 serial search. SKU is a proposed catalogue aid, not a PDF requirement.
- **Options:** globally unique serials; serial uniqueness within an agreed manufacturer/product scope; duplicate warnings reviewed by staff. Catalogue codes can remain optional/non-unique or become unique company-wide.
- **Recommend:** capture serials where applicable and flag duplicates until a reliable uniqueness scope is confirmed; retain optional non-unique SKU storage meanwhile. Approve case/space normalization before using it to merge or reject values.
- **Reason:** not every physical item has a serial and manufacturers may reuse labels. A different request key is not evidence of a new physical item.
- **Affected / blocking:** assets serial constraints, product SKU constraints and import matching; blocks strict uniqueness, not descriptive storage.
- **Approval:** Pending; examples from actual records required.

### ABD-09 — How should arrival condition be recorded?

**Question:** Which condition descriptions should staff use, and who verifies a damaged or uncertain arrival condition?

- **Source:** R-04/R-07/R-08 condition; R-02 statuses; R-09 damage.
- **Options:** recorded observations as free text; an approved condition list plus notes; a technical inspection checklist.
- **Recommend:** an approved short condition list plus notes and a named verifier for uncertainty/damage. Do not automatically mark every arrival as good or Available.
- **Reason:** condition and lifecycle status are different facts; the five PDF statuses are already fixed, but initial assessment and transitions are not.
- **Affected / blocking:** assets condition/initial state and receiving/return checks; blocks condition validation and operational initialization. Do not add a vocabulary now.
- **Approval:** Pending; condition list and verification responsibility required.

### ABD-10 — Who approves registration, and when may the asset be used?

**Question:** Who approves a newly recorded asset, may that person approve their own entry, and may allocation begin before approval?

- **Source:** R-01 immediate registration and R-10 required approval workflows.
- **Options:** immediate recorded registration with use blocked until approval; immediate recorded registration with explicitly authorized provisional use. Approval can have one or several named stages.
- **Recommend:** create the registration record immediately, keep approval state separate from physical lifecycle status, and block allocation until the designated approval completes. Management must name approvers, stages, delegation and self-approval rules.
- **Reason:** fulfills immediate registration and approval together. Waiting for approval before recording an arrival is not recommended as a compliant alternative.
- **Affected / blocking:** assets registration_state and registration/allocation workflows; blocks their implementation/activation, not existing arrival header.
- **Approval:** Pending; recommendation is not an approved authority matrix.

### ABD-11 — Who resolves inconsistent historical asset records?

**Question:** Who can decide whether duplicated/missing old LED labels refer to the same asset, and authorize a replacement label?

- **Source:** PDF manual Google Sheets context; R-02 identity, R-11 history, R-14 search.
- **Options:** preserve all labels without reconciliation; approve a reviewed old-to-new mapping; label every old asset again.
- **Recommend:** review a read-only source export, preserve original labels/source row references, and approve only necessary replacements with named accountability.
- **Reason:** prevents lost provenance and accidental merging. No export was provided or inspected in this task; no starting counter can be inferred.
- **Affected / blocking:** import provenance and asset-number collision policy; blocks legacy import, not unrelated catalog models.
- **Approval:** Pending; approved source, reviewer and mapping required.

### ABD-12 — What kinds of pooled items are in scope?

**Question:** Are pooled items reusable items that must be returned, consumable supplies, or both?

- **Source:** R-03 quantities; R-04 allocation; R-07 mandatory return; R-08 returns; R-13 totals.
- **Options:** reusable pooled stock; consumables handled in a separate clarified workflow; both with explicitly separate accounting/reporting rules.
- **Recommend:** begin with reusable pooled items under the existing return obligations; clarify consumable requirements separately before supporting consumption. Report quantities by product/unit, not by adding incompatible measures or counting lots as physical assets.
- **Reason:** quantity tracking must not silently introduce an exception to R-07 or a consumption/disposal shortcut.
- **Affected / blocking:** lots, balances, movements, allocations/returns and dashboards; blocks operational stock/outflow semantics. Lot metadata also needs ABD-01/02 and receipt lines.
- **Approval:** Pending; any consumable scope requires explicit requirements clarification, not implied policy approval.

### ABD-13 — How long must a saved submission remain protected against a late retry?

**Question:** After a mobile or network interruption, how long might staff retry an old submission, and how long may its minimal confirmation details be retained?

- **Source:** R-16 mobile entry; R-11 traceability. Retry retention is an implementation-support policy not specified by the PDF.
- **Options:** a defined retry period with expiry behavior; longer-lived duplicate markers with shorter-lived confirmations; indefinite retention (requires explicit justification).
- **Recommend:** approve a maximum retry period and a separate retention period for minimal confirmation data. Retain a duplicate marker or reject old retries after confirmation expiry, rather than silently treating the old request as new. Do not delete markers referenced by business history.
- **Reason:** protects against duplicate stock while limiting stored response data. Engineering chooses the key/hash/locking mechanics; management supplies operational timing and retention authority.
- **Affected / blocking:** shared idempotency lifecycle/cleanup and mobile commands. Core model design can use nullable expiry without assuming a duration, but activation/cleanup needs this decision.
- **Approval:** Pending; no number of days or automatic cleanup policy is approved.

## Existing approval dependencies, not reopened here

The pending [audit trust and permission decisions](../implementation/audit-permission-readiness.md) and [authentication/identity decisions](../architecture/authentication.md) still apply. This document does not select an identity provider, approve actor attribution or change audit redaction, history access or retention. R-11 remains partial. Stock adjustment/loss/disposal authority and return/repair transitions require their later workflow review; none is authorized through the receiving contract.

Prioritize ABD-01–05 for receipt-line and quantity metadata review, then ABD-07–10 for individual assets. ABD-06 governs discrepancy activation, ABD-11 imports, ABD-12 stock workflows and ABD-13 retry retention. Detailed sequencing and technical decisions are in the [updated implementation plan](../implementation/asset-foundation-plan.md).
