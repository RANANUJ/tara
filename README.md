# Tara

Tara is a local-first personal AI assistant. This repository currently contains only the M1 monorepo and development-tooling bootstrap: a static Next.js shell and a FastAPI health service. No authentication, AI, memory, voice, WebSocket, or product features are implemented yet.

## Prerequisites

- Node.js 24 or newer
- pnpm 11.9.0
- Python 3.12

## Setup

From the repository root:

```powershell
pnpm install

python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"
Copy-Item backend/.env.example backend/.env
```

`backend/.env` is local-only. Replace placeholder values only when a later milestone requires them; never commit it.

## Run

Open two terminals from the repository root. Activate the backend virtual environment in the backend terminal.

```powershell
pnpm dev:frontend
pnpm dev:backend
```

The frontend runs on `http://localhost:3000`. The backend runs on `http://127.0.0.1:8000` and currently exposes only:

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`

Equivalent PowerShell launchers are available in `scripts/development`.

## Validation Commands

Run these from the repository root after activating `backend/.venv`:

```powershell
pnpm lint:frontend
pnpm typecheck:frontend
pnpm test:frontend
pnpm build:frontend

pnpm lint:backend
pnpm typecheck:backend
pnpm test:backend
```

Run all checks together with:

```powershell
pnpm validate
```

## Repository Layout

```text
frontend/                 Next.js 15, React 19, TypeScript, Tailwind CSS v4
backend/                  Python 3.12 FastAPI package with src layout
contracts/                Future reviewed REST/WebSocket contract artifacts
scripts/development/      Local development launchers
docs/                     Product and engineering source documentation
.github/workflows/        Frontend and backend validation
```

## Scope Guardrails

- Tara is a responsive React + Next.js web application; Flutter is not used.
- This bootstrap does not implement product routes, the Guide Star, AI providers, memory stores, authentication, WebSockets, audio, or automation tools.
- Do not commit `.env` files, secrets, recordings, models, local databases, logs, exports, virtual environments, or build output.
- Read `AGENTS.md` and the architecture/security documents before extending the implementation.
