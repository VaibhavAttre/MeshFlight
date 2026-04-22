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

## Local LLM Setup For AI Scenario Assistant

The AI Scenario Assistant supports `Ollama`, `Gemini`, and `OpenAI` through the backend. The browser never talks to models directly.

### 1. Install Ollama

- Windows/macOS/Linux: [ollama.com/download](https://ollama.com/download)

### 2. Start Ollama

Start the Ollama app or service so the local HTTP API is running.

### 3. Pull the recommended model

```powershell
ollama pull qwen2.5-coder:7b
```

### 4. Test the model manually

```powershell
ollama run qwen2.5-coder:7b
```

### 5. Confirm the local API is reachable

```powershell
curl http://localhost:11434/api/tags
```

### 6. Configure the backend environment

Use the root [.env.example](C:\Users\vaibh\OneDrive\Desktop\MeshFlight\.env.example) as the template. The local AI section should look like:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
```

If you want to use a cloud provider from the UI selector instead, also configure one of:

```env
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
```

or

```env
OPENAI_AI_ASSIST_ENABLED=true
OPENAI_MAX_AI_ASSIST_REQUESTS_PER_DAY=3
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-5-nano
OPENAI_BASE_URL=https://api.openai.com/v1
```

OpenAI is paid API usage, so it stays disabled by default unless you intentionally enable it.

### 7. Start the backend and UI

```powershell
npm run dev:api
npm run dev:ui
```

### 8. Check provider health

The backend exposes:

- `GET /api/scenarios/ai-assist/health`

It verifies:

- the selected provider is configured
- Ollama is reachable when Ollama is selected
- the configured model is installed when the provider supports local model discovery

### 9. Test from the UI

Open the editor, click `AI Scenario`, and use a prompt like:

`Generate a small emergency response scenario with one gateway, three drones, six clients, one building blocking line-of-sight, and one interference zone. Use reasonable positions and metadata. Make the scenario name "small-emergency-response-test".`

The current editor-safe AI path represents interference pressure using supported editor objects such as vegetation zones or interference-spike events, so the result stays editable in the canvas.
