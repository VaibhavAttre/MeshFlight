# MeshFlight

MeshFlight is a Phase 0 monorepo for scenario authoring, schema validation, compilation, and early control-plane workflows for a self-healing aerial mesh simulation project.

Current repo focus:
- `0A` local setup and repo health
- `0B` shared contracts, fixtures, and validation
- `0C` editor MVP
- `0D` compiler MVP
- partial `0F` save/load/compile API flows

## Working Local Flows

- Frontend dev: `npm run dev:ui`
- Backend dev: `npm run dev:api`
- UI typecheck: `npm run typecheck:ui`
- UI build: `npm run build:ui`
- Python tests: `.venv\Scripts\python -m pytest -q`
- Python lint: `.venv\Scripts\python -m ruff check .`

## Repo Layout

- `apps/editor-ui` - React + TypeScript editor UI for scenario authoring
- `apps/api` - FastAPI control-plane shell for save/load/compile actions
- `services/scenario_compiler` - real scenario compiler service
- `packages/schema` - Pydantic source/compiled/runtime data contracts
- `packages/runtime_contracts` - runtime event contracts
- `artifacts/scenarios` - backend-managed saved scenario bundles and compiled outputs
- `tests/fixtures/scenarios` - canonical authored scenario fixtures for schema/compiler tests
- `tests/schema` - schema contract tests
- `tests/compiler` - compiler-focused tests

## Current Artifact Convention

Each saved scenario lives in its own bundle:

- `artifacts/scenarios/<scenario-id>/source/scenario.json`
- `artifacts/scenarios/<scenario-id>/compiled/compiled.json`
- `artifacts/scenarios/<scenario-id>/compiled/compile_report.json`

New saves auto-generate a unique scenario title/id when the requested name is already taken. Saving an already-open saved scenario updates that same bundle instead of creating a duplicate.
