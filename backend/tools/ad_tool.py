"""Advertisement placement policy utility."""

class AdvertisementTool:
    """Build ad-break recommendations that avoid back-to-back spots."""

    @staticmethod
    def placement(priority_ads: list[dict], max_spots: int = 3) -> list[dict]:
        """Select the highest-priority active ads with a bounded break length."""
        active = [ad for ad in priority_ads if ad.get("active", True)]
        return sorted(active, key=lambda ad: ad.get("priority", 0), reverse=True)[:max_spots]
