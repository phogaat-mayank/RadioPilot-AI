"""Tests for MusicDiscoveryTool multi-provider online music search."""

import pytest
from unittest.mock import AsyncMock, patch
from tools.music_discovery_tool import MusicDiscoveryTool


@pytest.mark.asyncio
async def test_music_discovery_empty_query() -> None:
    """Empty or blank queries immediately return an empty list without network calls."""
    tool = MusicDiscoveryTool()
    assert await tool.search("") == []
    assert await tool.search("   ") == []


@pytest.mark.asyncio
async def test_music_discovery_itunes_success() -> None:
    """Successful primary iTunes search returns structured track metadata."""
    tool = MusicDiscoveryTool()
    mock_items = [
        {
            "id": "1073359419",
            "title": "Tum Hi Ho",
            "artist": "Mithoon & Arijit Singh",
            "duration_seconds": 262,
            "release_date": "2013-03-16",
        }
    ]
    with patch.object(tool, "_search_itunes", new_callable=AsyncMock) as mock_itunes:
        mock_itunes.return_value = mock_items
        results = await tool.search("Tum Hi Ho", limit=5)
        assert len(results) == 1
        assert results[0]["title"] == "Tum Hi Ho"
        assert results[0]["artist"] == "Mithoon & Arijit Singh"
        mock_itunes.assert_awaited_once_with("Tum Hi Ho", 5)


@pytest.mark.asyncio
async def test_music_discovery_fallback_to_deezer_when_itunes_fails() -> None:
    """If iTunes fails or errors, Deezer fallback is seamlessly engaged."""
    tool = MusicDiscoveryTool()
    mock_deezer_items = [
        {
            "id": "deezer_123",
            "title": "Kesariya",
            "artist": "Arijit Singh",
            "duration_seconds": 268,
            "release_date": None,
        }
    ]
    with patch.object(tool, "_search_itunes", side_effect=Exception("iTunes timeout")), \
         patch.object(tool, "_search_deezer", new_callable=AsyncMock) as mock_deezer:
        mock_deezer.return_value = mock_deezer_items
        results = await tool.search("Kesariya", limit=5)
        assert len(results) == 1
        assert results[0]["title"] == "Kesariya"
        mock_deezer.assert_awaited_once_with("Kesariya", 5)


@pytest.mark.asyncio
async def test_music_discovery_fallback_to_musicbrainz_when_others_fail() -> None:
    """If both iTunes and Deezer fail, MusicBrainz is engaged."""
    tool = MusicDiscoveryTool()
    mock_mb_items = [
        {
            "id": "mb_abc",
            "title": "Shape of You",
            "artist": "Ed Sheeran",
            "duration_seconds": 233,
            "release_date": "2017-01-06",
        }
    ]
    with patch.object(tool, "_search_itunes", side_effect=Exception("iTunes error")), \
         patch.object(tool, "_search_deezer", side_effect=Exception("Deezer error")), \
         patch.object(tool, "_search_musicbrainz", new_callable=AsyncMock) as mock_mb:
        mock_mb.return_value = mock_mb_items
        results = await tool.search("Shape of You", limit=5)
        assert len(results) == 1
        assert results[0]["title"] == "Shape of You"
        mock_mb.assert_awaited_once_with("Shape of You", 5)


@pytest.mark.asyncio
async def test_music_discovery_all_providers_fail_returns_empty_list() -> None:
    """If all providers fail (e.g. offline station), tool returns [] instead of crashing."""
    tool = MusicDiscoveryTool()
    with patch.object(tool, "_search_itunes", side_effect=Exception("Network down")), \
         patch.object(tool, "_search_deezer", side_effect=Exception("Network down")), \
         patch.object(tool, "_search_musicbrainz", side_effect=Exception("Network down")):
        results = await tool.search("Any Song", limit=5)
        assert results == []
