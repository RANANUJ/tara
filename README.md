# Tara

Tara is a local-first personal AI assistant. This repository contains the M1 monorepo/tooling bootstrap and the M2 backend persistence foundation: a static Next.js shell, a FastAPI health service, and internal SQLite persistence infrastructure. No authentication, AI, ChromaDB, voice, WebSocket, agent, or product features are implemented yet.

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

## Database Migrations

Run migrations before starting the backend. Alembic uses a synchronous SQLite URL while the application uses SQLAlchemy's async `sqlite+aiosqlite` URL.

```powershell
.\backend\.venv\Scripts\Activate.ps1
python -m alembic -c backend/alembic.ini upgrade head
```

Create a reviewed migration after changing only internal persistence models:

```powershell
python -m alembic -c backend/alembic.ini revision --autogenerate -m "describe_change"
```

For a non-default database, supply a SQLite URL explicitly:

```powershell
python -m alembic -c backend/alembic.ini -x database_url="sqlite:///./data/tara.db" upgrade head
```

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
- M2 persists only internal foundational records through repositories and Alembic migrations. It exposes no new product API, authentication, AI, ChromaDB, WebSocket, voice, or scheduler behavior.
- Do not commit `.env` files, secrets, recordings, models, local databases, logs, exports, virtual environments, or build output.
- Read `AGENTS.md` and the architecture/security documents before extending the implementation.
