# Inventory AIOS Frontend

The Inventory AIOS frontend is a React + TypeScript + Vite application shell for the inventory management system. It currently contains responsive navigation and placeholder pages only; operational workflows will be added after the API contracts and business rules are approved.

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

Then open the local URL printed by Vite.

## Validation commands

```bash
npm run typecheck
npm run lint
npm run test
npm run build
```

Use `npm run test:watch` for an interactive test session. No backend, database, Grok API, authentication service, or inventory data is required by the current frontend shell.