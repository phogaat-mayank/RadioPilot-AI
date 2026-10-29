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

## Multi-agent RJ AI & Conversational Studio

The platform includes an advanced multi-turn conversational studio and supervisor graph with Scheduler, Playlist, RJ Script, News, Advertisement, Analytics, Music Director, and Memory agents. The RJ AI Conversational Studio powered by high-capacity reasoning models (`openai/gpt-oss-120b` via Groq) can answer **any question**—from general knowledge, science, mathematics, coding, and history to radio station programming, playlist curation, witty presenter links, listener engagement, and audio engineering.

Key features:
- **Universal Multi-turn Chat**: Full conversational memory, GitHub-flavored Markdown rendering, code snippet highlighting with one-click copy, and multi-model fallback cascading.
- **Voice Studio & TTS**: Hands-free voice recognition (Hindi, Hinglish, English) with intelligent intent routing and speech synthesis for RJ responses.
- **Specialist Quick Actions**: Instant generation for playlists, presenter scripts, and verified hourly news bulletins.
- **Persistence & Management**: Complete chat history per session with instant clearing and auto-scroll streams.
- **Autopilot & Approval Gates**: Seamless manual/autopilot toggles and operator approval workflows. See `docs/multi-agent-platform.md` for full topology details.
