"""LangGraph autopilot recommendation graph with typed state."""

from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from agents.roles import broadcast_agent, monitoring_agent, playback_agent, playlist_agent, scheduler_agent


class AutopilotState(TypedDict, total=False):
    """State carried through AI decision stages; it has no control handles."""
    mode: str
    queue: list[int]
    recommendation: dict


def _scheduler(state: AutopilotState) -> dict:
    """Run scheduler decision stage."""
    return {"recommendation": scheduler_agent(state)}


def _playlist(state: AutopilotState) -> dict:
    """Run playlist decision stage."""
    return {"recommendation": playlist_agent(state)}


def _playback_review(state: AutopilotState) -> dict:
    """Run non-executing playback review stage."""
    return {"recommendation": playback_agent(state["recommendation"])}


def _broadcast(state: AutopilotState) -> dict:
    """Run broadcast-policy stage."""
    return {"recommendation": broadcast_agent(state["recommendation"])}


def _monitor(state: AutopilotState) -> dict:
    """Run monitoring stage and produce final recommendation."""
    return {"recommendation": monitoring_agent(state["recommendation"])}


def build_autopilot_graph():
    """Build the checkpoint-compatible decision-only LangGraph."""
    graph = StateGraph(AutopilotState)
    graph.add_node("scheduler", _scheduler)
    graph.add_node("playlist", _playlist)
    graph.add_node("playback_review", _playback_review)
    graph.add_node("broadcast", _broadcast)
    graph.add_node("monitor", _monitor)
    graph.add_edge(START, "scheduler")
    graph.add_conditional_edges("scheduler", lambda state: "playlist" if state["mode"] == "AUTOPILOT" else "monitor")
    graph.add_edge("playlist", "playback_review")
    graph.add_edge("playback_review", "broadcast")
    graph.add_edge("broadcast", "monitor")
    graph.add_edge("monitor", END)
    return graph.compile()


autopilot_graph = build_autopilot_graph()
