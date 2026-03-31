# Local Setup

## Intended toolchain

- Node.js 24+
- npm 11+
- Python 3.11 preferred by the spec

## Current project setup

- Root npm workspaces for frontend packages
- Root Python dependency file for backend and service modules
- Shared environment variables in the repository root `.env.example`

## Next build steps

- create the shared schema models in `packages/schema`
- hand-author example scenarios in `artifacts/scenarios`
- scaffold the editor UI and API entrypoint around those contracts
