"""Schedule validation and conflict detection utility."""

from datetime import datetime, timedelta
from models.entities import Schedule


class ScheduleTool:
    """Validate planned clock slots before persistence."""

    @staticmethod
    def conflicts(candidate: datetime, schedules: list[Schedule], tolerance_minutes: int = 5) -> list[Schedule]:
        """Return events that overlap the candidate's protected time window."""
        window = timedelta(minutes=tolerance_minutes)
        return [schedule for schedule in schedules if abs(schedule.run_at - candidate) < window and schedule.enabled]
