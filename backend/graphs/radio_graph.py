"""Supervisor graph for multi-agent radio automation decisions."""

from langgraph.graph import END, START, StateGraph
from agents.radio_agents import AgentState, advertisement_agent, analytics_agent, memory_agent, music_director_agent, news_agent, playlist_agent, rj_script_agent, scheduler_agent, supervisor


def _route(state: AgentState) -> str:
    """Choose the graph edge matching the supervisor-selected agent."""
    return state["selected_agent"]


def _database(state: AgentState) -> dict:
    """Mark the decision ready for service-layer persistence."""
    return {"data": {**state.get("data", {}), "persistence": "required"}}


def _validate(state: AgentState) -> dict:
    """Reject empty agent outputs before any state-changing service action."""
    if not state.get("response", "").strip():
        return {"validation_error": "Agent produced an empty response"}
    return {"validation_error": ""}


def _response(state: AgentState) -> dict:
    """Finalize graph state without invoking playback or external side effects."""
    return {}


def build_radio_graph():
    """Build a typed, auditable supervisor graph with one node per agent."""
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor)
    graph.add_node("scheduler", scheduler_agent)
    graph.add_node("playlist", playlist_agent)
    graph.add_node("rj_script", rj_script_agent)
    graph.add_node("news", news_agent)
    graph.add_node("advertisement", advertisement_agent)
    graph.add_node("analytics", analytics_agent)
    graph.add_node("music_director", music_director_agent)
    graph.add_node("assistant", memory_agent)
    graph.add_node("database", _database)
    graph.add_node("validation", _validate)
    graph.add_node("finalize", _response)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", _route, {agent: agent for agent in ["scheduler", "playlist", "rj_script", "news", "advertisement", "analytics", "music_director", "assistant"]})
    for agent in ["scheduler", "playlist", "rj_script", "news", "advertisement", "analytics", "music_director", "assistant"]:
        graph.add_edge(agent, "database")
    graph.add_edge("database", "validation")
    graph.add_edge("validation", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


radio_graph = build_radio_graph()
