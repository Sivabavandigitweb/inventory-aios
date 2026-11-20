---
name: testing-quality
description: Plan and review Inventory AIOS quality coverage across Pytest, Vitest, permissions, workflows, and recovery behavior.
---

# Testing and quality

Use this skill when designing, implementing, or reviewing Inventory AIOS tests and quality checks.

- Use Pytest for backend and workflow coverage and Vitest for frontend behavior.
- Cover unit, integration, and end-to-end workflow behavior at the appropriate boundary; prioritize confirmed requirements and high-risk transitions.
- Test authentication, role permissions, validation failures, secure error handling, and unauthorized access paths.
- Verify duplicate prevention, transaction rollback, retries, interruption recovery, and audit-log behavior for state-changing workflows.
- Inspect state read-only before destructive-operation tests; use isolated fixtures and explicit cleanup rather than broad deletion.
- Treat unverified business assumptions as test gaps or decision records, not as silently approved behavior.
