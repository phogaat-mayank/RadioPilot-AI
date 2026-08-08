"""Music-library queries for AI selection."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.entities import Song


class MusicLibraryTool:
    """Retrieve candidate songs without leaking ORM mechanics to agents."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind to an injected async session."""
        self._session = session

    async def candidates(self, mood: str | None, limit: int = 100) -> list[Song]:
        """Find genre-matched songs, falling back to the full library."""
        statement = select(Song).order_by(Song.created_at.desc()).limit(limit)
        if mood:
            statement = statement.where(Song.genre.ilike(f"%{mood}%"))
        songs = list((await self._session.scalars(statement)).all())
        if songs or not mood:
            return songs
        return list((await self._session.scalars(select(Song).order_by(Song.created_at.desc()).limit(limit))).all())
