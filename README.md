# MeshFlight

MeshFlight is a monorepo for **2D mesh networking scenario authoring**, **schema validation**, **compilation into a structured runtime bundle**, and **early simulation / control-plane workflows** aimed at aerial relay / self-healing mesh experiments.

The codebase prioritizes a **small, inspectable pipeline**: authored scenarios → validated JSON → compiled graph / schedule → optional discrete-time simulation (`services/sim_core`) → artifacts the editor can replay.

---

## Goals

- **Authoring**: edit gateways, drones, clients, obstacles, demand zones, and chaos events on a canvas with predictable persistence.
- **Contracts**: a single source of truth for scenario shape (`ScenarioSource`) and compiled output (`CompiledScenario`) via Pydantic models in `packages/schema`.
- **Compilation**: turn editor scenarios into normalized entities, obstacle indexing, candidate connectivity edges, waypoint hints, mobility bounds, and a **runtime schedule** (traffic + chaos) aligned with the real compiler in `services/scenario_compiler`.
- **Simulation**: a deterministic tick loop in `services/sim_core` (links → routing → limited drone movement toward disconnected clients → snapshots). Not a full RF or mobility simulator; it exists to **exercise compiled data** and produce **replayable timelines**.
- **Integration**: FastAPI backend for save/load/compile/simulate; React editor for visual authoring and **snapshot replay** scrubbing after a run.

---

## Major components

| Area | Path | Role |
|------|------|------|
| Editor UI | `apps/editor-ui` | Vite + React + Zustand canvas; scenario CRUD via API; compile; AI assist modal; **Simulate** + replay bar driven by snapshot JSON |
| API | `apps/api` | FastAPI app (`meshflight_api`): scenarios, compile, AI assist health/generate, **POST simulate** + **GET run snapshots** |
| Schema | `packages/schema` | `ScenarioSource`, `CompiledScenario`, shared enums / geometry types |
| Compiler | `services/scenario_compiler` | CLI + library: `compile_scenario()` writes `compiled.json` + `compile_report.json` |
| Simulator | `services/sim_core` | Runner, state, links, routing, movement, events, snapshots, I/O, CLI |
| Fixtures | `tests/fixtures/scenarios` | Example authored scenarios for compiler / sim tests |
| Local storage | `artifacts/scenarios` | Per-scenario bundles created by the API (`source/`, `compiled/`, `runs/`) |

---

## Features (current)

- **Canvas authoring**: place and edit entities and obstacles; optional auto demand zones; chaos event list; client–drone link visualization based on geometry (editor-side heuristic).
- **Save / load**: scenarios persisted under `artifacts/scenarios/<scenario-id>/source/scenario.json`.
- **Compile**: produces `compiled/` artifacts used by simulation and tests.
- **AI scenario assistant** (optional): backend calls Ollama, Gemini, or OpenAI to produce a **small JSON plan**; counts and placement are merged server-side so prompts drive outcomes; contextual chaos events attach after a valid build. See [Local LLM setup](#local-llm-setup-ai-scenario-assistant) below.
- **Simulate + replay**: from the editor toolbar, save → compile → run the simulator → fetch snapshots; a replay strip scrubs tick indices and applies node positions (and failed-drone styling) from snapshot data. Snapshot count is **1 + ⌊duration_s / tick_duration_s⌋** (e.g. 28 s @ 1 s → 29 frames) unless those parameters change in the client call.

---

## Tooling

- **Node.js** (npm workspaces): root scripts proxy to `apps/editor-ui`.
- **Python 3.11+** recommended; virtualenv at repo root (`.venv`).
- **pytest** + **ruff** (see `pyproject.toml`). Tests assume repo-root `pythonpath` includes `services` (already configured for pytest).
- **FastAPI / Uvicorn** for the API; **Vite** for the UI.
- **Ollama** (or cloud keys) only for AI assist paths; models never run in the browser.

---

## Quick start

Prerequisites: Node.js, Python, a `.venv` with dev dependencies installed (`pip install -e` / project requirements as documented in individual app READMEs if present).

```powershell
# API (from repo root; ensures services/ is importable via meshflight_api.main)
npm run dev:api

# Editor (separate shell)
npm run dev:ui
```

Other useful scripts:

| Script | Purpose |
|--------|---------|
| `npm run dev:api:stable` | API without auto-reload |
| `npm run typecheck:ui` | TypeScript check for the editor |
| `npm run build:ui` | Production build of the editor |
| `npm run lint:ui` | ESLint for the editor |

Python checks (examples):

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
```

---

## Artifact layout

Each scenario bundle under `artifacts/scenarios/<scenario-id>/`:

- `source/scenario.json` — authored `ScenarioSource`
- `compiled/compiled.json` — `CompiledScenario` from the compiler
- `compiled/compile_report.json` — counts, hashes, config echo
- `runs/<run-id>/` — optional simulation outputs (`snapshots.jsonl`, `events.jsonl`, `summary.json`, `run_config.json`)

New saves receive a unique `scenario_id` when the requested title collides with an existing bundle; re-saving the same open scenario updates that bundle in place.

---

## Configuration

- **API base URL for the editor**: set `VITE_API_BASE_URL` if the API is not at `http://127.0.0.1:8000` (see `apps/editor-ui/src/lib/scenarioApi.ts`).
- **Environment**: copy [.env.example](.env.example) to `.env` at the repo root when present; the API loads it on startup (`meshflight_api.env`).

---

## Local LLM setup (AI scenario assistant)

The assistant is **backend-only**; the browser talks to the MeshFlight API, which talks to the configured provider.

### Ollama (typical local path)

1. Install from [ollama.com/download](https://ollama.com/download).
2. Start the Ollama service so `http://localhost:11434` responds.
3. Pull a model, e.g. `ollama pull qwen2.5-coder:7b`.
4. In `.env`, set for example:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
```

### Optional cloud providers

Configure one of the following blocks as needed; OpenAI stays opt-in because it is billed usage.

```env
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
```

```env
OPENAI_AI_ASSIST_ENABLED=true
OPENAI_MAX_AI_ASSIST_REQUESTS_PER_DAY=3
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-nano
OPENAI_BASE_URL=https://api.openai.com/v1
```

### Health check

`GET /api/scenarios/ai-assist/health` reports whether the selected provider is configured and (for Ollama) whether the model appears installed.

### Behavior notes

The AI path produces a **plan JSON**, not raw full-scenario coordinates. The API merges prompt-derived counts, runs a deterministic builder, attaches **contextual chaos events** from scenario structure, and validates against the schema. Unsupported natural-language asks (e.g. full 3D terrain) are rejected up front with a suggested rephrase.

---

## Further reading

- `apps/api/README.md` — API-specific notes
- `apps/editor-ui/README.md` — UI dev server and build
- `services/scenario_compiler/README.md` — compiler CLI
- `services/sim_core/README.md` — simulator (`sim_core`) overview
- `docs/architecture/README.md` — placeholder for deeper architecture notes

---

## License / status

Private research / prototype repository (`"private": true` in `package.json`). Work-in-progress; APIs and UX evolve with the mesh authoring and simulation track.
