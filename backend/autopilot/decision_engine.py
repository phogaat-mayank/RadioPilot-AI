"""Pure policy engine and LangGraph supervisor for structured autopilot actions."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from autopilot.autopilot_state import ActionType, AutopilotAction, StationState


class DecisionGraphState(TypedDict, total=False):
    """Decision graph state; it deliberately contains no service or engine handle."""

    station: StationState
    candidates: list[AutopilotAction]


class DecisionEngine:
    """Translate station state into actions without executing any media operation."""

    def __init__(self, idle_threshold_seconds: float = 20.0) -> None:
        self._idle_threshold = idle_threshold_seconds
        self._graph = self._build_supervisor_graph()

    def decide(self, state: StationState) -> AutopilotAction:
        """Run the supervisor graph and select the highest-priority policy outcome."""
        if state.manual_override or not state.autopilot_enabled or state.current_mode.upper() != "AUTOPILOT":
            return AutopilotAction(ActionType.NO_ACTION, "Autopilot is disabled or manual override is active", priority=1000)
        outcome = self._graph.invoke({"station": state, "candidates": []})
        candidates = outcome.get("candidates", [])
        return min(candidates, key=lambda action: action.priority) if candidates else AutopilotAction(ActionType.NO_ACTION, "No action is currently required", priority=1000)

    def _build_supervisor_graph(self):
        """Build named, decision-only supervisor stages required by the architecture."""
        graph = StateGraph(DecisionGraphState)
        graph.add_node("SchedulerAgent", self._scheduler_agent)
        graph.add_node("PlaylistAgent", self._playlist_agent)
        graph.add_node("QueueAgent", self._queue_agent)
        graph.add_node("BroadcastAgent", self._broadcast_agent)
        graph.add_node("MonitoringAgent", self._monitoring_agent)
        graph.add_edge(START, "SchedulerAgent")
        graph.add_edge("SchedulerAgent", "PlaylistAgent")
        graph.add_edge("PlaylistAgent", "QueueAgent")
        graph.add_edge("QueueAgent", "BroadcastAgent")
        graph.add_edge("BroadcastAgent", "MonitoringAgent")
        graph.add_edge("MonitoringAgent", END)
        return graph.compile()

    @staticmethod
    def _append(state: DecisionGraphState, action: AutopilotAction | None) -> dict:
        candidates = list(state.get("candidates", []))
        if action is not None:
            candidates.append(action)
        return {"candidates": candidates}

    def _scheduler_agent(self, state: DecisionGraphState) -> dict:
        """Observe schedule state; ScheduleExecutor is the sole due-event dispatcher."""
        return self._append(state, None)

    def _playlist_agent(self, state: DecisionGraphState) -> dict:
        station = state["station"]
        if station.ads_due:
            return self._append(state, AutopilotAction(ActionType.PLAY_ADS, "Advertisement break is due", priority=20))
        return self._append(state, None)

    def _queue_agent(self, state: DecisionGraphState) -> dict:
        station = state["station"]
        if not station.queue and not station.live_mode:
            return self._append(state, AutopilotAction(ActionType.LOAD_QUEUE, "Playback queue is empty", {"exclude_song_ids": [station.current_song.id] if station.current_song else []}, priority=40))
        return self._append(state, None)

    def _broadcast_agent(self, state: DecisionGraphState) -> dict:
        station = state["station"]
        if station.live_mode and not station.mic_enabled:
            return self._append(state, AutopilotAction(ActionType.END_LIVE, "Live mode has no enabled microphone", priority=30))
        return self._append(state, None)

    def _monitoring_agent(self, state: DecisionGraphState) -> dict:
        station = state["station"]
        health = station.system_health
        if not health.media_healthy or not health.playback_healthy or health.idle_seconds >= self._idle_threshold:
            return self._append(state, AutopilotAction(ActionType.RECOVER_PLAYBACK, "Playback health requires recovery", {"idle_seconds": health.idle_seconds, "last_error": health.last_error}, priority=5))
        return self._append(state, None)


def build_autopilot_supervisor_graph(idle_threshold_seconds: float = 20.0):
    """Expose the LangGraph supervisor for integration tests and observability."""
    return DecisionEngine(idle_threshold_seconds)._graph
