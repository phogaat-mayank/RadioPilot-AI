"""Controller behavior tests."""

import pytest
from models.entities import Song
from playback.controller import PlaybackController


@pytest.mark.asyncio
async def test_queue_play_pause_resume() -> None:
    """Playback state transitions remain serialized and predictable."""
    controller = PlaybackController()
    song = Song(id=1, title="Test", artist="Artist", file_path="/tmp/test.mp3", duration_seconds=10)
    await controller.queue(song)
    await controller.play()
    assert (await controller.state())["status"] == "playing"
    await controller.pause()
    assert (await controller.state())["status"] == "paused"
    await controller.resume()
    assert (await controller.state())["current_song"].id == 1


@pytest.mark.asyncio
async def test_clear_queue() -> None:
    """Queue items can be cleared in bulk."""
    controller = PlaybackController()
    song1 = Song(id=1, title="Song 1", artist="Artist 1", file_path="/tmp/1.mp3")
    song2 = Song(id=2, title="Song 2", artist="Artist 2", file_path="/tmp/2.mp3")
    await controller.queue(song1)
    await controller.queue(song2)
    assert len((await controller.state())["queue"]) == 2
    cleared = await controller.clear_queue()
    assert cleared == 2
    assert len((await controller.state())["queue"]) == 0


@pytest.mark.asyncio
async def test_repository_delete_all_songs() -> None:
    """Deleting all songs clears playlist associations and nullifies playback history."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from models.entities import Base, Playlist, PlaylistSong, PlaybackHistory
    from repositories.radio import RadioRepository

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = RadioRepository(session)
        song1 = await repo.add_song(Song(title="Track A", artist="Artist A", file_path="/tmp/a.mp3"))
        song2 = await repo.add_song(Song(title="Track B", artist="Artist B", file_path="/tmp/b.mp3"))
        playlist = await repo.add_playlist(Playlist(name="Main"))
        await repo.add_to_playlist(playlist, song1)
        await repo.add_to_playlist(playlist, song2)

        session.add(PlaybackHistory(song_id=song1.id, action="play", performed_by="tester"))
        await session.commit()

        songs_before = await repo.list_songs()
        assert len(songs_before) == 2

        deleted = await repo.delete_all_songs()
        assert deleted == 2

        songs_after = await repo.list_songs()
        assert len(songs_after) == 0

        # Check playlist songs were removed
        pl = await repo.get_playlist(playlist.id)
        assert len(pl.items) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_duplicate_song_detection() -> None:
    """Duplicate songs with case-insensitive matching on title and artist are detected."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from models.entities import Base
    from repositories.radio import RadioRepository

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = RadioRepository(session)
        await repo.add_song(Song(title="Bohemian Rhapsody", artist="Queen", file_path="/tmp/bohemian.mp3"))

        # Exact match
        dup1 = await repo.find_duplicate_song("Bohemian Rhapsody", "Queen")
        assert dup1 is not None

        # Case-insensitive and trimmed match
        dup2 = await repo.find_duplicate_song("  bohemian rhapsody  ", "queen")
        assert dup2 is not None

        # Non-duplicate
        non_dup = await repo.find_duplicate_song("Another One Bites the Dust", "Queen")
        assert non_dup is None

    await engine.dispose()
