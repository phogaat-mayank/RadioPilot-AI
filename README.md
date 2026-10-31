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

---

## Free Self-Hosted AI DJ Voice Engine (Piper Neural TTS)

RadioPilot AI features an integrated, 100% free, self-hosted Text-to-Speech AI DJ Voice Engine powered by [Piper TTS](https://github.com/rhasspy/piper). It runs local ONNX neural voice models directly on CPU with zero ElevenLabs or paid API dependencies.

### Verified Voice Models & Licenses

The system automatically manages 4 real, production-tested Piper neural voice models (stored in `media/piper_voices/`):

| Voice ID | RJ Name | Language | Gender | Source Dataset / Quality | License |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `hi_IN-priyamvada-medium` | **RJ Priyamvada** | हिन्दी (Hindi) | Female | AI4Bharat IndicNLP (22.05 kHz) | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |
| `hi_IN-pratham-medium` | **RJ Pratham** | हिन्दी (Hindi) | Male | AI4Bharat IndicNLP (22.05 kHz) | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |
| `en_US-lessac-medium` | **RJ Lessac** | English (US) | Female | Blizzard Challenge 2013 / CSTR | Free Non-Commercial Research |
| `en_US-ryan-medium` | **RJ Ryan** | English (US) | Male | RyanSpeech Dataset (22.05 kHz) | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |

Full license texts are preserved in `backend/services/piper_licenses.md`.

### Strict Playback Sequencing Architecture

Audio playback follows a deterministic sequential state pipeline that guarantees **never allowing two audio streams to play simultaneously**:

```
[Song 1 Playing] ────────────────────────────────────────────────────────┐
       │                                                                 │
       │ (In background: AI DJ pre-generates next announcement via Piper)│
       ▼                                                                 │
[Song 1 Ends] (Browser fires `track_ended`)                              │
       │                                                                 │
       ▼                                                                 │
[Check AI DJ Settings & Ready Announcement]                              │
       ├─► [Announcement Ready] ──► Sets `active_announcement`           │
       │                                 │                               │
       │                                 ▼                               │
       │                           Single `<audio>` element streams      │
       │                           `/api/v1/tts/stream/{announcement_id}`│
       │                                 │                               │
       │                                 ▼                               │
       │                           [Announcement Ends] (`announcement_ended`)
       │                                 │                               │
       │                                 ▼                               │
       └─► [No Announcement / TTS Muted] ┴─► Clears `active_announcement`│
                                               │                         │
                                               ▼                         │
                                       [Song 2 Starts in Player] ◄───────┘
```

- **Zero Audio Overlap Guarantee**: A single native HTML5 `<audio>` element (`audioRef` in `GlassAudioPlayer.tsx`) is used for both music tracks and DJ announcements. The browser stream URL switches sequentially from song blob to announcement blob to next song blob.
- **Fail-Safe Fallback**: If the AI DJ engine is muted or an inference error occurs, `track_ended` seamlessly skips straight to the next scheduled song without delay.

### AI DJ API Endpoints

- `GET /api/v1/tts/voices` — Catalog of supported voice models with language, gender, sample rate, and license.
- `GET /api/v1/tts/settings` — Current AI DJ configuration (enabled, language, voice, frequency, volume, toggles).
- `PUT /api/v1/tts/settings` — Update AI DJ configuration.
- `POST /api/v1/tts/preview` — Audition a voice model with instant WAV playback (used by dashboard Test Voice button).
- `POST /api/v1/tts/synthesize` — Synthesize custom announcement text into a standalone audio file.
- `POST /api/v1/tts/manual-announcement` — Broadcast an immediate or next-transition custom announcement.
- `GET /api/v1/tts/stream/{announcement_id}` — Stream generated 22.05 kHz 16-bit PCM WAV announcement audio.
- `POST /api/v1/station/announcement-ended` — Signal completion of on-air announcement and trigger next song transition.

### Running Test Verification

To execute the test suite (unit tests, neural inference verification, playback sequencing, and fallback):

```bash
# Run complete test suite (32 tests across entire project)
docker compose exec api pytest -v

# Run AI DJ specific lifecycle & Piper TTS tests
docker compose exec api pytest tests/test_ai_dj_full_lifecycle.py tests/test_tts_voice_engine.py -v
```
