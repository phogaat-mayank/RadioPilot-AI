"""Specialist multi-agent nodes for RadioPilot AI."""

from __future__ import annotations

from typing import TypedDict
from tools.analytics_tool import AnalyticsTool
from tools.news_tool import NewsTool
from tools.script_tool import ScriptTool


class AgentState(TypedDict, total=False):
    """Serializable state shared by the supervisor graph."""
    request_type: str
    prompt: str
    metadata: dict
    selected_agent: str
    response: str
    data: dict
    requires_approval: bool
    validation_error: str


AGENT_BY_REQUEST = {"schedule": "scheduler", "playlist": "playlist", "script": "rj_script", "news": "news", "ads": "advertisement", "analyze": "analytics", "autopilot": "music_director"}


def supervisor(state: AgentState) -> dict:
    """Route a request to one specialist according to explicit intent."""
    intent = state.get("request_type", "chat")
    selected = AGENT_BY_REQUEST.get(intent, "assistant")
    return {"selected_agent": selected}


def scheduler_agent(state: AgentState) -> dict:
    """Draft a schedule action for later conflict validation."""
    return {"response": f"Schedule proposal prepared: {state['prompt']}", "data": {"intent": "schedule"}, "requires_approval": True}


def playlist_agent(state: AgentState) -> dict:
    """Describe music policy; concrete song selection remains in a service tool."""
    return {"response": f"Playlist plan prepared for {state.get('metadata', {}).get('mood', 'station rotation')}.", "data": {"intent": "playlist"}, "requires_approval": True}


def rj_script_agent(state: AgentState) -> dict:
    """Generate presenter script copy."""
    return {"response": ScriptTool.compose(state["prompt"]), "data": {"intent": "script"}, "requires_approval": False}


def news_agent(state: AgentState) -> dict:
    """Generate a radio-friendly bulletin from supplied verified headlines."""
    headlines = state.get("metadata", {}).get("headlines", [])
    return {"response": NewsTool.bulletin(headlines), "data": {"intent": "news"}, "requires_approval": True}


def advertisement_agent(state: AgentState) -> dict:
    """Draft an approval-gated, non-consecutive ad placement plan."""
    return {"response": f"Advertisement break plan prepared: {state['prompt']}", "data": {"intent": "ads", "max_back_to_back": 1}, "requires_approval": True}


def analytics_agent(state: AgentState) -> dict:
    """Analyze supplied aggregate metrics."""
    result = AnalyticsTool.recommend(state.get("metadata", {}).get("metrics", {}))
    return {"response": result["recommendation"], "data": result, "requires_approval": False}


def music_director_agent(state: AgentState) -> dict:
    """Recommend an editorial music direction for the autopilot cycle."""
    return {"response": "Music Director recommends a balanced, artist-separated rotation for the next hour.", "data": {"intent": "autopilot"}, "requires_approval": True}


def memory_agent(state: AgentState) -> dict:
    """Serve as a transparent memory-aware assistant response node."""
    return {"response": f"RJ AI: {state['prompt']}", "data": {"intent": "chat"}, "requires_approval": False}
