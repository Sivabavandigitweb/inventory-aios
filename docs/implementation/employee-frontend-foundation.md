# Task 9A / 9A.2 — Employee Management frontend foundation

Status: fictional local preview only at `/employees`. No employee source or backend is connected. No authentication adapter, employee write, synchronization operation, or database access is performed. The manual registration UI introduced in Task 9A was removed in Task 9A.2 after the direction changed to authoritative-source synchronization.

## Requirements and current contracts

The original PDF R-05 requires employee ID, name, department, team, designation, joining date and linked assets. R-06 requires transfer/promotion changes with complete history; R-07 requires exit clearance and retained records; R-14 requires name/ID and organization search; R-16 requires mobile employee updates. The PDF does not mandate manual entry in Inventory AIOS, but the mobile update channel and source-status/clearance interaction need management confirmation. See the [synchronization architecture](../architecture/employee-synchronization.md).

The current backend exposes guarded `GET /api/v1/employees` (`EmployeePage`), `GET /api/v1/employees/{id}` (`EmployeeRead`), and a fail-closed `POST /api/v1/employees` using `EmployeeCreate`. The frontend mirrors only the read fields. The backend registration route/service remain intact and disabled; this task changes no backend contract. Future removal or replacement with an internal sync command needs a separate review and corresponding backend test updates.

## Implemented UI and boundary

The page has summary cards, search, department and status filters, paginated directory, loading/empty/error states, responsive table cards and an accessible details dialog. Details show only current `EmployeeRead` fields and label allocation, return, organizational history and exit sections as unavailable or planned. The mock provider contains only fictional `DEMO-` records. Active matches the backend default; inactive previews the R-07 label. No other production status vocabulary is assumed. Summary counts are mock calculations, not a backend endpoint. The shell's administrator label is a placeholder and does not constitute authentication.

A compact synchronization section shows connection `Not connected`, last successful sync `Not available`, availability `Unavailable`, and a disabled `Sync Employees` action. It contains no fabricated timestamp or result. The Add Employee action, registration dialog, form, state and form-specific styles are removed. There is no network call or silent mock fallback after an API failure.

The typed `EmployeeDirectoryProvider` keeps preview data separate from a future authorized adapter. That adapter must obtain organization labels and summary counts from approved sources, report failures directly, and honor backend permissions. The browser must not access the source database. Employee source authority, synchronization permissions, audit grants, identity mapping and R-11 before/after tracking remain pending. Frontend tests cover directory behavior, details, mock labeling, sync-disabled state and absence of manual registration; they do not prove database or source integration.
