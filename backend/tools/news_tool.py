"""News bulletin normalization utility."""

class NewsTool:
    """Transform supplied verified headlines into radio-safe copy."""

    @staticmethod
    def bulletin(headlines: list[str]) -> str:
        """Produce a concise, attribution-preserving hourly bulletin."""
        clean = [headline.strip() for headline in headlines if headline.strip()][:5]
        if not clean:
            return "No verified headlines are currently available. We will return with the latest news at the top of the hour."
        return "Hourly news update. " + " ".join(f"{index + 1}. {headline}." for index, headline in enumerate(clean))
