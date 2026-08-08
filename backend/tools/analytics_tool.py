"""Station analytics recommendation utility."""

class AnalyticsTool:
    """Convert operator metrics into actionable programming recommendations."""

    @staticmethod
    def recommend(metrics: dict) -> dict:
        """Return transparent recommendations from supplied aggregate metrics."""
        skips = float(metrics.get("skips", 0))
        plays = max(float(metrics.get("plays", 0)), 1.0)
        skip_rate = round(skips / plays, 3)
        return {"skip_rate": skip_rate, "recommendation": "Increase genre rotation and reduce repeat frequency" if skip_rate > 0.2 else "Current music rotation is healthy"}
