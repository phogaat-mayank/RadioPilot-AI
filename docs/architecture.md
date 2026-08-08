# Architecture

RadioPilot AI applies clean architecture boundaries:

```text
Dashboard → FastAPI routes → RadioService → PlaybackController → AudioEngine → FM output
                              ↑
                    LangGraph recommendations only
```

The agent workflow receives a typed, serializable state and can recommend actions. It has no import path or handle to `PlaybackController`. Only a user/API/scheduler service command can invoke audio execution.

`SystemState` maintains the AUTOPILOT/MANUAL switch independently of audio state, so ownership changes never interrupt a playing track. Scheduled events are persisted in the `schedules` table and re-registered at startup.
