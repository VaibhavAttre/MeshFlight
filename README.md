# MeshFlight

Phase 0 scaffold for the MeshFlight monorepo.

This repository is set up around the Phase 0 plan:
- monorepo layout for apps, services, packages, artifacts, docs, and tests
- frontend workspace for the editor UI
- backend Python environment for API, compiler, simulator, and shared schema work
- placeholder docs and runbooks so architecture and contracts can be captured as they stabilize

## Phase 0 focus

This scaffold is intentionally infrastructure-first. It does not include MeshFlight feature logic yet.

## Planned local workflows

- Frontend: `cmd /c npm run dev --workspace @meshflight/editor-ui`
- Backend: `.venv\\Scripts\\python -m uvicorn apps.api.main:app --reload`
- Python checks: `.venv\\Scripts\\python -m pytest`
- Python lint: `.venv\\Scripts\\python -m ruff check .`

## Structure

- `apps/editor-ui` - React + TypeScript + Vite workspace
- `apps/api` - FastAPI entrypoint and control-plane shell
- `services` - compiler, simulator, replay, and baseline policy modules
- `packages` - neutral shared contracts and generated types
- `artifacts` - saved scenarios, runs, and reports
- `docs` - architecture notes, API docs, and runbooks
- `tests` - schema, compiler, sim, API, and e2e test areas
