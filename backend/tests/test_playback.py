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
