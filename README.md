# RadioPilot AI

RadioPilot AI is a hybrid FM radio automation platform. The dashboard and API can operate in manual or autopilot mode without stopping the current broadcast.

## Safety boundary

AI workflows produce recommendations only. `PlaybackController` is the only component permitted to execute playback operations; it can be backed by VLC today and Liquidsoap later.

## Run with Docker

1. Copy `.env.example` to `.env` and change `JWT_SECRET` and `ADMIN_PASSWORD`.
2. Run `docker compose up --build`.
3. Open `http://localhost:3000`; sign in with the configured admin account.

The API is available at `http://localhost:8000`, with OpenAPI documentation at `/docs`.

## Local backend

Use Python 3.12, create a virtual environment, then run `pip install -r backend/requirements.txt`. Set `DATABASE_URL=sqlite+aiosqlite:///./radiopilot.db` for a self-contained local run, then execute `uvicorn main:app --reload` from `backend`.

## Resetting the administrator password

After changing `ADMIN_EMAIL` or `ADMIN_PASSWORD` in `.env`, run `docker compose exec api python -m scripts.reset_admin_password`. This updates only the configured administrator account and does not delete music, schedules, or station history.

## Architecture

`api` owns transport, `services` owns use cases, repositories isolate persistence, and `playback` owns audio execution. WebSockets broadcast state changes. APScheduler persists scheduled work to PostgreSQL. The LangGraph workflow is invoked only by the autopilot coordinator and returns a recommendation for the service layer to validate.

## Multi-agent RJ AI

The platform now includes a supervisor graph with Scheduler, Playlist, RJ Script, News, Advertisement, Analytics, Music Director, and Memory agents. New authenticated `/api/v1/ai/*` routes provide RJ chat, specialist actions, task history, mode controls, and approval/rejection of proposed decisions. Celery Worker, Beat, and Flower services are included in Docker Compose for the hourly autopilot cycle. See `docs/multi-agent-platform.md` for the topology and model setup.
