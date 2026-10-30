"""Full-access station control tools and action executor for NOVA."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import logging
import re
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import PlaylistSong, Schedule, Song
from repositories.radio import RadioRepository
from schemas.radio import PlaylistCreate, ScheduleCreate
from services.radio import RadioService
from tools.music_discovery_tool import MusicDiscoveryTool
from tools.news_tool import NewsTool
from tools.script_tool import ScriptTool
from tools.youtube_tool import YouTubeTool

logger = logging.getLogger(__name__)

# Common Hindi Devanagari transliteration mapping for music searches
HINDI_TO_LATIN = {
    "शेडी": "shady",
    "चीमा": "cheema",
    "यारी": "yaari",
    "टेंशन": "tension",
    "रेबेल": "rebel",
    "जैकपॉट": "jackpot",
    "सीईओ": "ceo",
    "कार्टेल": "cartel",
    "स्नैप": "snap",
    "स्काईफुल": "skyfull",
    "सुमित": "sumit",
    "गोस्वामी": "goswami",
    "धांधा": "dhanda",
    "न्योलीवाला": "nyoliwala",
    "अर्जन": "arjan",
    "ढिल्लों": "dhillon",
    "ब्लैक": "black",
    "राइड": "ride",
    "बैरण": "bairan",
    "छोरी": "chori",
    "किस्से": "kisse",
    "कहानी": "kahani",
    "महक": "mahak",
    "मित्तर": "mittar",
    "गाना": "song",
    "गीत": "song",
}

DEVANAGARI_CHARS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ा": "a", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ं": "n", "ँ": "n", "्": "", "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au"
}


def transliterate_hindi(text: str) -> str:
    """Approximate Hindi words to Latin characters for library matching."""
    lower = text.lower()
    for hi, la in HINDI_TO_LATIN.items():
        lower = lower.replace(hi, f" {la} ")
    res = []
    for char in lower:
        res.append(DEVANAGARI_CHARS.get(char, char))
    return "".join(res)


def clean_search_term(term: str) -> str:
    """Strip common conversational stopwords."""
    t = transliterate_hindi(term.lower())
    t = re.sub(r"\b(play|song|music|track|gaana|baja|chala|bajaao|chalaao|baja do|chala do|kripya|please|the|a|an|suno|sunao|सुनो|सुनाओ|गाना|गीत|बजाओ|चलाओ)\b", " ", t)
    return re.sub(r"[^a-zA-Z0-9\s]", " ", t).strip()


def find_matching_song(query: str, songs: list[Song]) -> Song | None:
    """Find the best matching song in the library by id, title, or artist."""
    q_str = str(query).strip()
    if not q_str:
        return None

    # Match exact ID
    if q_str.isdigit():
        q_id = int(q_str)
        for s in songs:
            if s.id == q_id:
                return s

    cleaned_q = clean_search_term(q_str)
    tokens = [tok for tok in cleaned_q.split() if len(tok) >= 2]

    # Exact lowercase substring match
    for s in songs:
        t_clean = s.title.lower()
        a_clean = s.artist.lower()
        if cleaned_q and (cleaned_q in t_clean or cleaned_q in a_clean):
            return s

    # Token overlap match
    if tokens:
        best_song = None
        best_score = 0
        for s in songs:
            combined = f"{s.title} {s.artist}".lower()
            score = sum(1 for tok in tokens if tok in combined)
            if score > best_score:
                best_score = score
                best_song = s
        if best_score > 0 and best_song is not None:
            return best_song

    return None


NOVA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "play_song",
            "description": "Search the station music library and immediately play the requested song on air. Accepts song title, artist, or song ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_query": {
                        "type": "string",
                        "description": "Title, artist, or song ID to play (e.g. 'Shady', 'Yaari On Top', 'Cheema Y', or '216')"
                    }
                },
                "required": ["song_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_playback",
            "description": "Control live radio station playback: pause, resume, stop, skip to next song, or go to previous song.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "resume", "stop", "skip", "previous"],
                        "description": "Playback action to execute"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Adjust the radio station broadcast volume (0 to 100 percent).",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Target volume percentage from 0 to 100"
                    }
                },
                "required": ["level"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_station_status",
            "description": "Get real-time radio station status: currently playing song, playback state (playing/paused/stopped), station mode (AUTOPILOT or MANUAL), volume level, and broadcast queue.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_autopilot",
            "description": "Turn station Autopilot mode ON or OFF. When ON, the AI autopilot decision engine automatically manages playlists, news, and rotations. When OFF, manual RJ control is active.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "True to start Autopilot mode, False to switch to Manual mode"
                    }
                },
                "required": ["enabled"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_library",
            "description": "List or search songs in the station music library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search term to filter library songs by title or artist"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "enqueue_song",
            "description": "Add a song from the library to the upcoming broadcast queue without interrupting the currently playing song.",
            "parameters": {
                "type": "object",
                "properties": {
                    "song_query": {
                        "type": "string",
                        "description": "Title, artist, or ID of the song to queue"
                    }
                },
                "required": ["song_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clear_queue",
            "description": "Clear all pending upcoming songs from the live broadcast queue.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_playlists",
            "description": "List all existing playlists in the radio station along with their song counts.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_playlist",
            "description": "Get the songs and details of a specific playlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "playlist_name_or_id": {
                        "type": "string",
                        "description": "Name or numeric ID of the playlist"
                    }
                },
                "required": ["playlist_name_or_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_playlist",
            "description": "Create a new playlist on the radio station and optionally add songs to it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new playlist"
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description of the playlist"
                    },
                    "song_queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of song titles or artists to include in the playlist"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_playlist",
            "description": "Queue or immediately play an entire playlist on the radio station.",
            "parameters": {
                "type": "object",
                "properties": {
                    "playlist_name_or_id": {
                        "type": "string",
                        "description": "Name or ID of the playlist to play"
                    },
                    "interrupt_current": {
                        "type": "boolean",
                        "description": "If True, stops the current song and starts this playlist immediately. If False, queues it up."
                    }
                },
                "required": ["playlist_name_or_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_song_to_playlist",
            "description": "Add a library song to an existing playlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "playlist_name_or_id": {
                        "type": "string",
                        "description": "Name or ID of the playlist"
                    },
                    "song_query": {
                        "type": "string",
                        "description": "Title, artist, or ID of the song to add"
                    }
                },
                "required": ["playlist_name_or_id", "song_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_event",
            "description": "Schedule a news bulletin or playlist on the radio station calendar for a specific airtime.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the scheduled event (e.g. 'Evening News' or 'Weekend Vibes')"
                    },
                    "event_type": {
                        "type": "string",
                        "enum": ["news", "playlist"],
                        "description": "Type of event: 'news' for a news broadcast or 'playlist' for music"
                    },
                    "run_at": {
                        "type": "string",
                        "description": "When to broadcast: ISO timestamp (e.g. '2026-10-30T10:00:00') or relative offset like '+30m', '+1h', '+2h'"
                    },
                    "playlist_name_or_id": {
                        "type": "string",
                        "description": "Required if event_type is 'playlist': Name or ID of the playlist to air"
                    },
                    "prep_minutes": {
                        "type": "integer",
                        "description": "Minutes before airtime to prepare the news (5, 10, 15, 30)"
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "description": "Duration of news bulletin in seconds (45, 60, 90)"
                    }
                },
                "required": ["name", "event_type", "run_at"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_schedules",
            "description": "List all upcoming scheduled events (news bulletins and playlists) on the radio station.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_schedule",
            "description": "Delete or cancel a scheduled event by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "integer",
                        "description": "The ID of the schedule to delete"
                    }
                },
                "required": ["schedule_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_music_online",
            "description": "Search external music databases (iTunes/Deezer) for song metadata, artist releases, and tracks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Artist or song to search online"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_youtube",
            "description": "Search YouTube for a song and retrieve the direct watch link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Song name or query to search on YouTube"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compose_rj_script",
            "description": "Compose an energetic radio presenter script, intro, outro, or bridge for a track or topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_or_mood": {
                        "type": "string",
                        "description": "Topic, mood, or song for the RJ script"
                    }
                },
                "required": ["topic_or_mood"]
            }
        }
    }
]


def parse_schedule_time(run_at_str: str, tz_name: str = "Asia/Kolkata") -> datetime:
    """Parse user or LLM schedule time into a timezone-aware UTC datetime.
    
    Accurately maps:
    1. Simple times ('12:00', '12:00 PM', '5pm') to the station's local timezone (Asia/Kolkata / IST = UTC+05:30).
    2. Relative offsets ('+15m', '+1h', '+30min').
    3. Naive ISO timestamps ('2026-10-30T12:00:00') -> treated as local station time, converted to UTC.
    4. Offset ISO timestamps ('2026-10-30T12:00:00+05:30' or '2026-10-30T06:30:00Z') -> converted directly to UTC.
    """
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")

    now_local = datetime.now(tz)
    s = run_at_str.strip()

    # 1. Relative offset (+15m, +1h, +30min, etc.)
    offset_match = re.match(r"^\+(\d+)\s*(m|min|minute|minutes|h|hr|hour|hours)$", s, re.I)
    if offset_match:
        qty = int(offset_match.group(1))
        unit = offset_match.group(2).lower()
        delta = timedelta(hours=qty) if "h" in unit else timedelta(minutes=qty)
        return (now_local + delta).astimezone(timezone.utc)

    # 2. Time-only string (e.g. '12:00', '12:00 PM', '12:00:00', '5pm', '17:30', '9:15 am')
    time_match = re.match(r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm)?$", s, re.I)
    if time_match:
        hr = int(time_match.group(1))
        mn = int(time_match.group(2) or 0)
        sc = int(time_match.group(3) or 0)
        ampm = (time_match.group(4) or "").lower()
        if ampm == "pm" and hr < 12:
            hr += 12
        elif ampm == "am" and hr == 12:
            hr = 0
        candidate = now_local.replace(hour=hr, minute=mn, second=sc, microsecond=0)
        if candidate <= now_local:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    # 3. ISO or date-time string
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # Naive ISO string without timezone was intended as local station time (Asia/Kolkata)
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Default fallback: 10 minutes from now
    return (now_local + timedelta(minutes=10)).astimezone(timezone.utc)


async def execute_nova_tool(
    name: str,
    args: dict[str, Any],
    session: AsyncSession,
    actor: str = "NOVA",
) -> dict[str, Any]:
    """Execute a radio station tool with full autonomous privileges."""
    radio_service = RadioService(session)
    radio_repo = RadioRepository(session)

    try:
        if name == "play_song":
            song_query = str(args.get("song_query", "")).strip()
            library = list(await radio_repo.list_songs())
            song = find_matching_song(song_query, library)
            if not song:
                sample = [{"id": s.id, "title": s.title, "artist": s.artist} for s in library[:8]]
                return {
                    "status": "not_found",
                    "query": song_query,
                    "message": f"Song '{song_query}' was not found in the station library.",
                    "available_library_sample": sample,
                }
            state = await radio_service.play(song.id, actor)
            return {
                "status": "playing",
                "song_id": song.id,
                "title": song.title,
                "artist": song.artist,
                "duration_seconds": song.duration_seconds,
                "playback_status": state.status,
                "message": f"Now broadcasting '{song.title}' by {song.artist} on air.",
            }

        elif name == "control_playback":
            action = str(args.get("action", "")).lower().strip()
            if action in {"play", "resume"}:
                state = await radio_service.play(None, actor)
            elif action in {"pause", "stop", "skip", "previous"}:
                state = await radio_service.command(action, actor)
            else:
                return {"status": "error", "message": f"Unsupported action '{action}'"}
            return {
                "status": "success",
                "action": action,
                "playback_status": state.status,
                "current_song": state.current_song.title if state.current_song else None,
            }

        elif name == "set_volume":
            level = max(0, min(100, int(args.get("level", 50))))
            state = await radio_service.set_volume(level, actor)
            return {"status": "success", "volume": level, "message": f"Volume set to {level}%."}

        elif name == "get_station_status":
            state = await radio_service.state()
            station_state = await radio_repo.get_state()
            return {
                "status": "success",
                "mode": station_state.mode.value,
                "playback_status": state.status,
                "volume": state.volume,
                "current_song": {
                    "id": state.current_song.id,
                    "title": state.current_song.title,
                    "artist": state.current_song.artist,
                    "duration_seconds": state.current_song.duration_seconds,
                } if state.current_song else None,
                "queue_count": len(state.queue),
                "next_in_queue": state.queue[0].title if state.queue else None,
            }

        elif name == "set_autopilot":
            enabled = bool(args.get("enabled", True))
            from services.ai import AIService
            ai_status = await AIService(session).set_autopilot(enabled, actor)
            return {
                "status": "success",
                "mode": ai_status.mode,
                "autopilot_enabled": ai_status.autopilot_enabled,
                "message": f"Station switched to {'AUTOPILOT' if enabled else 'MANUAL'} mode.",
            }

        elif name == "list_library":
            query = args.get("query")
            songs = list(await radio_repo.list_songs(str(query) if query else None))
            return {
                "status": "success",
                "count": len(songs),
                "songs": [{"id": s.id, "title": s.title, "artist": s.artist, "duration": s.duration_seconds} for s in songs[:25]],
            }

        elif name == "enqueue_song":
            song_query = str(args.get("song_query", "")).strip()
            library = list(await radio_repo.list_songs())
            song = find_matching_song(song_query, library)
            if not song:
                return {"status": "not_found", "message": f"Song '{song_query}' not found in library."}
            state = await radio_service.enqueue_song(song.id, actor)
            return {
                "status": "queued",
                "song_id": song.id,
                "title": song.title,
                "artist": song.artist,
                "queue_count": len(state.queue),
                "message": f"Queued '{song.title}' to play next.",
            }

        elif name == "clear_queue":
            state = await radio_service.clear_queue(actor)
            return {"status": "success", "message": "Broadcast queue cleared."}

        elif name == "list_playlists":
            playlists = list(await radio_repo.list_playlists())
            return {
                "status": "success",
                "playlists": [{"id": p.id, "name": p.name, "song_count": len(p.items)} for p in playlists],
            }

        elif name == "get_playlist":
            query = str(args.get("playlist_name_or_id", "")).strip()
            playlists = list(await radio_repo.list_playlists())
            target = None
            if query.isdigit():
                target = await radio_repo.get_playlist(int(query))
            else:
                for p in playlists:
                    if query.lower() in p.name.lower():
                        target = await radio_repo.get_playlist(p.id)
                        break
            if not target:
                return {"status": "not_found", "message": f"Playlist '{query}' not found."}
            return {
                "status": "success",
                "id": target.id,
                "name": target.name,
                "songs": [{"id": item.song.id, "title": item.song.title, "artist": item.song.artist} for item in target.items],
            }

        elif name == "create_playlist":
            name_val = str(args.get("name", "Nova Mix")).strip() or "Nova Mix"
            desc = str(args.get("description", "Curated by NOVA")).strip()
            song_queries = args.get("song_queries", [])

            # Ensure unique name to avoid Postgres unique constraint violations
            existing_pls = list(await radio_repo.list_playlists())
            existing_names = {p.name.lower() for p in existing_pls}
            final_name = name_val
            counter = 2
            while final_name.lower() in existing_names:
                final_name = f"{name_val} ({counter})"
                counter += 1

            playlist = await radio_service.create_playlist(PlaylistCreate(name=final_name, description=desc))

            added_songs = []
            if song_queries and isinstance(song_queries, list):
                library = list(await radio_repo.list_songs())
                for sq in song_queries:
                    matched = find_matching_song(str(sq), library)
                    if matched:
                        await radio_repo.add_to_playlist(playlist, matched)
                        added_songs.append({"id": matched.id, "title": matched.title})

            await session.commit()
            await radio_service.emit_state()

            return {
                "status": "created",
                "playlist_id": playlist.id,
                "name": playlist.name,
                "added_songs": added_songs,
                "message": f"Playlist '{playlist.name}' created with {len(added_songs)} song(s).",
            }

        elif name == "play_playlist":
            query = str(args.get("playlist_name_or_id", "")).strip()
            interrupt = bool(args.get("interrupt_current", False))
            playlists = list(await radio_repo.list_playlists())
            target_id = None
            if query.isdigit():
                target_id = int(query)
            else:
                for p in playlists:
                    if query.lower() in p.name.lower():
                        target_id = p.id
                        break
            if target_id is None:
                return {"status": "not_found", "message": f"Playlist '{query}' not found."}
            state = await radio_service.run_playlist(target_id, actor, interrupt_current=interrupt)
            return {
                "status": "playing_playlist",
                "playlist_id": target_id,
                "interrupt_current": interrupt,
                "message": f"Playlist started on broadcast.",
            }

        elif name == "add_song_to_playlist":
            pl_query = str(args.get("playlist_name_or_id", "")).strip()
            song_query = str(args.get("song_query", "")).strip()
            playlists = list(await radio_repo.list_playlists())
            target_pl = None
            if pl_query.isdigit():
                target_pl = await radio_repo.get_playlist(int(pl_query))
            else:
                for p in playlists:
                    if pl_query.lower() in p.name.lower():
                        target_pl = await radio_repo.get_playlist(p.id)
                        break
            if not target_pl:
                return {"status": "not_found", "message": f"Playlist '{pl_query}' not found."}

            library = list(await radio_repo.list_songs())
            song = find_matching_song(song_query, library)
            if not song:
                return {"status": "not_found", "message": f"Song '{song_query}' not found in library."}

            await radio_repo.add_to_playlist(target_pl, song)
            return {
                "status": "added",
                "playlist": target_pl.name,
                "song": song.title,
                "message": f"Added '{song.title}' to playlist '{target_pl.name}'.",
            }

        elif name == "schedule_event":
            sched_name = str(args.get("name", "Scheduled Broadcast")).strip()
            event_type = str(args.get("event_type", "playlist")).strip().lower()
            run_at_str = str(args.get("run_at", "")).strip()
            playlist_name = str(args.get("playlist_name_or_id", "")).strip()
            prep_minutes = int(args.get("prep_minutes", 5))
            duration_seconds = int(args.get("duration_seconds", 60))

            # Robust schedule time parsing with local station timezone (Asia/Kolkata / IST)
            station_tz = ZoneInfo("Asia/Kolkata")
            run_at_dt = parse_schedule_time(run_at_str, "Asia/Kolkata")

            resolved_playlist_id = None
            if event_type == "playlist" and playlist_name:
                playlists = list(await radio_repo.list_playlists())
                if playlist_name.isdigit():
                    resolved_playlist_id = int(playlist_name)
                else:
                    for p in playlists:
                        if playlist_name.lower() in p.name.lower():
                            resolved_playlist_id = p.id
                            break

            metadata = {}
            if event_type == "news":
                metadata = {
                    "preparation_minutes": prep_minutes,
                    "duration_seconds": duration_seconds,
                    "mix": ["headlines", "weather", "station"],
                }

            sched = await radio_service.schedule(
                ScheduleCreate(
                    name=sched_name,
                    event_type=event_type,
                    playlist_id=resolved_playlist_id,
                    run_at=run_at_dt,
                    enabled=True,
                    metadata_json=metadata,
                )
            )
            await session.commit()
            from scheduler.service import station_scheduler
            station_scheduler.register_schedule(
                sched.id,
                sched.event_type,
                sched.playlist_id,
                sched.run_at,
                sched.metadata_json,
            )
            await radio_service.emit_state()

            local_time_display = sched.run_at.astimezone(station_tz).strftime("%I:%M %p").lstrip("0")
            local_date_display = sched.run_at.astimezone(station_tz).strftime("%Y-%m-%d %I:%M %p IST")
            return {
                "status": "scheduled",
                "id": sched.id,
                "name": sched.name,
                "event_type": sched.event_type,
                "run_at": sched.run_at.isoformat(),
                "local_time": local_date_display,
                "message": f"Scheduled '{sched.name}' ({sched.event_type}) for {local_time_display} today ({local_date_display}).",
            }

        elif name == "list_schedules":
            schedules = list(await radio_repo.list_schedules(upcoming_only=True))
            station_tz = ZoneInfo("Asia/Kolkata")
            return {
                "status": "success",
                "schedules": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "event_type": s.event_type,
                        "run_at": s.run_at.isoformat(),
                        "local_time": s.run_at.astimezone(station_tz).strftime("%I:%M %p IST"),
                        "enabled": s.enabled,
                    }
                    for s in schedules
                ],
            }

        elif name == "delete_schedule":
            sched_id = int(args.get("schedule_id", 0))
            sched = await radio_repo.get_schedule(sched_id)
            if not sched:
                return {"status": "not_found", "message": f"Schedule {sched_id} not found."}
            await radio_repo.delete_schedule(sched)
            return {"status": "deleted", "schedule_id": sched_id, "message": f"Schedule {sched_id} removed."}

        elif name == "search_music_online":
            query = str(args.get("query", "")).strip()
            results = await MusicDiscoveryTool().search(query, 5)
            return {"status": "success", "query": query, "results": results}

        elif name == "search_youtube":
            query = str(args.get("query", "")).strip()
            url, autoplay = await YouTubeTool().play_url(query)
            return {"status": "success", "query": query, "url": url, "autoplay": autoplay}

        elif name == "compose_rj_script":
            topic = str(args.get("topic_or_mood", "station bridge")).strip()
            script = ScriptTool.compose(topic)
            return {"status": "success", "topic": topic, "script": script}

        return {"status": "error", "message": f"Unknown tool '{name}'"}

    except Exception as ex:
        logger.exception("Error executing Nova tool '%s': %s", name, ex)
        return {"status": "error", "error": str(ex)}


def detect_direct_station_intent(prompt: str) -> tuple[str, dict[str, Any]] | None:
    """Fast deterministic parser for common direct voice/text station commands."""
    p = prompt.strip().lower()

    # Autopilot switches
    if any(phrase in p for phrase in ["start autopilot", "turn on autopilot", "enable autopilot", "autopilot on", "autopilot chalu", "autopilot chalao", "ऑटोपायलट चालू"]):
        return ("set_autopilot", {"enabled": True})
    if any(phrase in p for phrase in ["stop autopilot", "turn off autopilot", "disable autopilot", "autopilot off", "manual mode", "manual chalu", "manual chalao", "ऑटोपायलट बंद"]):
        return ("set_autopilot", {"enabled": False})

    # Playback commands
    if p in {"pause", "pause music", "stop music", "gaana roko", "gaana rok do", "music rok do", "pause radio", "रुक जाओ", "पॉज़ करो", "रोको"}:
        return ("control_playback", {"action": "pause"})
    if p in {"resume", "resume music", "continue music", "play music", "gaana chalao", "continue", "रेज़्यूम करो", "चालू करो"}:
        return ("control_playback", {"action": "resume"})
    if any(phrase in p for phrase in ["skip", "next song", "next track", "skip track", "agla gaana", "अगला गाना", "आगे बढ़ाओ"]):
        return ("control_playback", {"action": "skip"})
    if any(phrase in p for phrase in ["previous song", "pichla gaana", "पिछला गाना"]):
        return ("control_playback", {"action": "previous"})

    # Volume controls
    vol_match = re.search(r"(?:volume|awaz|sound|आवाज़)\s*(?:to|ko|pe|at|=|set to)?\s*(\d{1,3})", p)
    if vol_match:
        lvl = max(0, min(100, int(vol_match.group(1))))
        return ("set_volume", {"level": lvl})

    # Clear queue
    if any(phrase in p for phrase in ["clear queue", "clear live queue", "queue saaf karo", "क्यू साफ़ करो"]):
        return ("clear_queue", {})

    # Station status
    if any(phrase in p for phrase in ["station status", "what is playing", "what song is playing", "kya chal raha hai", "current song", "क्या बज रहा है", "कौन सा गाना"]):
        return ("get_station_status", {})

    # Direct play song
    play_match = (
        re.match(r"^(?:please\s+)?(?:play|chalao|bajao|suno|sunao)\s+(?:song\s+|gaana\s+)?(.+)$", p) or
        re.match(r"^(.+?)\s+(?:gaana\s+)?(?:chalao|bajao|baja do|chala do|play karo)$", p) or
        re.match(r"^(?:कृपया\s*)?(?:गाना\s*)?(.+?)\s*(?:बजाओ|चलाओ|सुनाओ)$", prompt)
    )
    if play_match:
        cand = play_match.group(1).strip()
        if len(cand) >= 2 and not any(w in cand for w in ["autopilot", "playlist", "status", "queue"]):
            return ("play_song", {"song_query": cand})

    return None

