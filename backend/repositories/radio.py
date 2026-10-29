"""Repository layer for station resources."""

from collections.abc import Sequence
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.entities import PlaybackHistory, Playlist, PlaylistSong, Schedule, Song, SystemState, User


class RadioRepository:
    """Encapsulate station persistence queries."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to one unit-of-work session."""
        self.session = session

    async def find_user(self, email: str) -> User | None:
        """Return a user by e-mail address."""
        return await self.session.scalar(select(User).where(User.email == email.lower()))

    async def add_user(self, user: User) -> User:
        """Persist a user."""
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_songs(self, query: str | None = None) -> Sequence[Song]:
        """List songs, optionally filtered by title or artist."""
        statement = select(Song).order_by(Song.created_at.desc())
        if query:
            term = f"%{query}%"
            statement = statement.where((Song.title.ilike(term)) | (Song.artist.ilike(term)))
        return (await self.session.scalars(statement)).all()

    async def get_song(self, song_id: int) -> Song | None:
        """Fetch one song."""
        return await self.session.get(Song, song_id)

    async def find_duplicate_song(self, title: str, artist: str) -> Song | None:
        """Find an existing library song matching title and artist."""
        clean_title = title.strip().lower()
        clean_artist = artist.strip().lower()
        statement = select(Song).where(
            func.lower(func.trim(Song.title)) == clean_title,
            func.lower(func.trim(Song.artist)) == clean_artist,
        )
        existing = await self.session.scalar(statement)
        if existing:
            return existing
        if clean_artist in {"unknown artist", "unknown", ""}:
            return await self.session.scalar(
                select(Song).where(
                    func.lower(func.trim(Song.title)) == clean_title,
                    func.lower(func.trim(Song.artist)).in_(["unknown artist", "unknown", ""]),
                )
            )
        return None

    async def add_song(self, song: Song) -> Song:
        """Persist a song."""
        self.session.add(song)
        await self.session.commit()
        await self.session.refresh(song)
        return song

    async def delete_song(self, song: Song) -> None:
        """Delete a song while retaining historical playback audit records."""
        await self.session.execute(update(PlaybackHistory).where(PlaybackHistory.song_id == song.id).values(song_id=None))
        await self.session.execute(delete(PlaylistSong).where(PlaylistSong.song_id == song.id))
        await self.session.delete(song)
        await self.session.commit()

    async def delete_all_songs(self) -> int:
        """Delete every song from the library while retaining audit history."""
        await self.session.execute(update(PlaybackHistory).values(song_id=None))
        await self.session.execute(delete(PlaylistSong))
        result = await self.session.execute(delete(Song))
        await self.session.commit()
        return result.rowcount

    async def list_playlists(self) -> Sequence[Playlist]:
        """List playlists."""
        return (await self.session.scalars(select(Playlist).order_by(Playlist.name))).all()

    async def get_playlist(self, playlist_id: int) -> Playlist | None:
        """Fetch a playlist and its ordered audio assets."""
        statement = select(Playlist).options(selectinload(Playlist.items).selectinload(PlaylistSong.song)).where(Playlist.id == playlist_id)
        return await self.session.scalar(statement)

    async def add_playlist(self, playlist: Playlist) -> Playlist:
        """Persist a playlist."""
        self.session.add(playlist)
        await self.session.commit()
        await self.session.refresh(playlist)
        return playlist

    async def delete_playlist(self, playlist: Playlist) -> None:
        """Delete a playlist, its membership rows, and dependent schedule links."""
        await self.session.execute(update(Schedule).where(Schedule.playlist_id == playlist.id).values(playlist_id=None, enabled=False))
        await self.session.delete(playlist)
        await self.session.commit()

    async def add_to_playlist(self, playlist: Playlist, song: Song) -> PlaylistSong:
        """Append a song only once to a playlist."""
        current = await self.session.scalar(select(PlaylistSong).where(PlaylistSong.playlist_id == playlist.id, PlaylistSong.song_id == song.id))
        if current:
            return current
        next_position = (await self.session.scalar(select(PlaylistSong.position).where(PlaylistSong.playlist_id == playlist.id).order_by(PlaylistSong.position.desc()).limit(1)) or -1) + 1
        item = PlaylistSong(playlist_id=playlist.id, song_id=song.id, position=next_position)
        self.session.add(item)
        await self.session.commit()
        return item

    async def reorder_playlist(self, playlist: Playlist, song_ids: list[int]) -> None:
        """Replace playlist order after validating all supplied song IDs."""
        items = (await self.session.scalars(select(PlaylistSong).where(PlaylistSong.playlist_id == playlist.id))).all()
        mapping = {item.song_id: item for item in items}
        if set(song_ids) != set(mapping):
            raise ValueError("Song IDs must match the current playlist contents")
        for position, song_id in enumerate(song_ids):
            mapping[song_id].position = position
        await self.session.commit()

    async def get_state(self) -> SystemState:
        """Return the singleton station state, creating it when absent."""
        state = await self.session.get(SystemState, 1)
        if state is None:
            state = SystemState(id=1)
            self.session.add(state)
            await self.session.commit()
            await self.session.refresh(state)
        return state

    async def add_schedule(self, schedule: Schedule) -> Schedule:
        """Persist a scheduled event."""
        self.session.add(schedule)
        await self.session.commit()
        await self.session.refresh(schedule)
        return schedule

    async def list_schedules(self) -> Sequence[Schedule]:
        """List schedule events chronologically."""
        return (await self.session.scalars(select(Schedule).order_by(Schedule.run_at))).all()

    async def get_schedule(self, schedule_id: int) -> Schedule | None:
        """Fetch one schedule event."""
        return await self.session.get(Schedule, schedule_id)

    async def delete_schedule(self, schedule: Schedule) -> None:
        """Remove a schedule event."""
        await self.session.delete(schedule)
        await self.session.commit()
