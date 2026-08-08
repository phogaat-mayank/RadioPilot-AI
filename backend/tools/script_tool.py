"""RJ script composition utility."""

class ScriptTool:
    """Generate concise, broadcast-ready copy with an explicit tone."""

    @staticmethod
    def compose(prompt: str, tone: str = "friendly, professional, energetic") -> str:
        """Create safe presenter copy from an operator brief."""
        return f"[{tone.title()}] {prompt.strip()} Thanks for staying with us on RadioPilot FM."
