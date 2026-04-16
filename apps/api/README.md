# API

Phase 0 FastAPI shell for compile, run lifecycle, replay, and event streaming.

Current Phase 0 endpoints:
- `GET /api/health`
- `GET /api/scenarios`
- `GET /api/scenarios/{scenario_id}`
- `POST /api/scenarios`
- `POST /api/scenarios/{scenario_id}/compile`

Artifacts written by these routes:
- source scenarios: `artifacts/scenarios/source/*.scenario.json`
- compiled scenarios: `artifacts/scenarios/compiled/*.compiled.json`

Run locally:
```powershell
.venv\Scripts\python -m uvicorn meshflight_api.main:app --app-dir apps/api/src --reload
```

Planned next responsibilities:
- scenario save, list, and compile endpoints
- run lifecycle endpoints
- WebSocket runtime event stream
- replay artifact access
