"""Multi-agent supervisor graph tests."""

import pytest
from graphs.radio_graph import radio_graph


@pytest.mark.asyncio
async def test_supervisor_routes_script_to_rj_agent() -> None:
    """A script request reaches the script specialist and validates output."""
    result = await radio_graph.ainvoke({"request_type": "script", "prompt": "Welcome listeners", "metadata": {}})
    assert result["selected_agent"] == "rj_script"
    assert "Welcome listeners" in result["response"]
    assert result["validation_error"] == ""
