# Multi-agent upgrade

The upgrade is additive: existing `/station`, `/library`, `/playlists`, `/schedules`, and authentication routes remain unchanged.

```text
api/routes/ai.py → services/ai.py → graphs/radio_graph.py
                                  ├── agents/radio_agents.py
                                  ├── tools/
                                  └── repositories/ai.py → ai_* tables
```

`RadioService` and `PlaybackController` remain the only path to audio commands. The LangGraph agents can propose playlists, schedules, ads, news, scripts, and analytics actions, but proposals requiring a broadcast or scheduling change are saved in `ai_decisions` for an RJ to approve or reject.

## Provider setup

Configure LiteLLM with `LITELLM_MODEL` (for example a Gemini, Groq, OpenRouter, or OpenAI LiteLLM model identifier) and `LITELLM_API_KEY`. Without those variables, RJ AI runs a deterministic offline fallback, which keeps the platform testable and prevents silent external calls.

## Background automation

Celery Beat invokes the hourly workflow. It exits immediately in manual mode. In autopilot mode it requests schedule, playlist, script, news, and ad recommendations, persists every result, and creates approval-gated decisions where required.
