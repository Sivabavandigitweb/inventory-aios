# Inventory AIOS Frontend

The Inventory AIOS frontend is a React + TypeScript + Vite application shell for the inventory management system. It contains responsive navigation and fictional previews for the inventory dashboard, assets, employees, allocations, returns, repairs, exit clearance, approvals, notifications, and reports. The Employee Management page previews a future authoritative-source sync; manual registration has been removed, and the sync action and live backend access remain disabled.

## Technology

- React and TypeScript
- Vite
- React Router
- ESLint
- Vitest and React Testing Library

## Local setup

From this directory:

```bash
npm install
npm run dev
```

Then open `http://localhost:5173/employees` (or the URL printed by Vite if the port differs). This route shows fictional `DEMO-` records only and makes no backend request.

## Validation commands

```bash
npm run typecheck
npm run lint
npm run test
npm run build
```

Use `npm run test:watch` for an interactive test session. No backend, database, Grok API, authentication service, or inventory data is required by the current frontend shell.
