"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ListMusic,
  LogOut,
  Music2,
  Pause,
  Play,
  Plus,
  Radio,
  Search,
  SkipForward,
  Trash2,
  Volume1,
  Volume2,
  VolumeX,
  WandSparkles,
  X,
} from "lucide-react";
import AIConsole from "../components/AIConsole";
import GlassAudioPlayer from "../components/GlassAudioPlayer";
import OperationsWorkspace from "../components/OperationsWorkspace";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Song = { id: number; title: string; artist: string; duration_seconds: number; file_path: string };
type Station = {
  status: string;
  mode: "MANUAL" | "AUTOPILOT";
  volume: number;
  current_song: Song | null;
  current_position_seconds: number;
  playback_revision: number;
  queue: Song[];
};

function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function formatApiError(detail: unknown): string {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const field = Array.isArray((item as { loc?: unknown[] }).loc)
            ? (item as { loc: unknown[] }).loc.slice(1).join(".")
            : "";
          const msg = (item as { msg?: string }).msg || (item as { message?: string }).message || JSON.stringify(item);
          return field ? `${field}: ${msg}` : String(msg);
        }
        return String(item);
      })
      .join("; ");
  }
  if (typeof detail === "object" && detail !== null) {
    if ("msg" in detail) return String((detail as { msg: unknown }).msg);
    if ("message" in detail) return String((detail as { message: unknown }).message);
    return JSON.stringify(detail);
  }
  return String(detail);
}

async function request(path: string, token: string, init: RequestInit = {}) {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    const raw = await response.json().catch(() => ({ detail: response.statusText }));
    const errorMsg = formatApiError(raw?.detail ?? response.statusText);
    const error = new Error(errorMsg) as Error & {
      status?: number;
    };
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("admin@radiopilot.local");
  const [password, setPassword] = useState("");
  const [station, setStation] = useState<Station | null>(null);
  const [songs, setSongs] = useState<Song[]>([]);
  const [quickFilter, setQuickFilter] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [navSection, setNavSection] = useState<"dashboard" | "library" | "playlists" | "scheduler" | "ai">("dashboard");
  const [operationsTab, setOperationsTab] = useState<"library" | "playlists" | "scheduler" | "logs">("library");
  const [lastVolume, setLastVolume] = useState<number>(75);
  const [localVolume, setLocalVolume] = useState<number>(75);
  const isChangingVolumeRef = useRef<boolean>(false);
  const volumeDebounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const handleNav = (target: "dashboard" | "library" | "playlists" | "scheduler" | "ai") => {
    setNavSection(target);
    if (target === "dashboard") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else if (target === "library" || target === "playlists" || target === "scheduler") {
      setOperationsTab(target);
      const el = document.getElementById("operations-section");
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (target === "ai") {
      const el = document.getElementById("ai-console-section");
      el?.scrollIntoView({ behavior: "smooth" });
    }
  };

  const refresh = async (activeToken = token) => {
    if (!activeToken) return;
    const [current, library] = await Promise.all([
      request("/station/status", activeToken),
      request("/library/songs", activeToken),
    ]);
    setStation(current);
    setSongs(library);
  };

  useEffect(() => {
    const stored = localStorage.getItem("radiopilot_token");
    if (stored) setToken(stored);
  }, []);

  useEffect(() => {
    void refresh().catch((e: Error & { status?: number }) => {
      if (e.status === 401) {
        localStorage.removeItem("radiopilot_token");
        setToken(null);
        setError("Your session expired. Please sign in again.");
      } else setError(e.message);
    });
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const timer = window.setInterval(() => void refresh().catch(() => undefined), 2500);
    const handleStationRefresh = () => {
      void refresh().catch(() => undefined);
    };
    window.addEventListener("station-refresh", handleStationRefresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("station-refresh", handleStationRefresh);
    };
  }, [token]);

  useEffect(() => {
    if (!token || !station?.current_song) {
      setAudioUrl(null);
      return;
    }
    const controller = new AbortController();
    let objectUrl = "";
    void fetch(`${API}/library/songs/${station.current_song.id}/stream`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("Could not load audio for browser playback");
        return response.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setAudioUrl(objectUrl);
      })
      .catch((fetchError) => {
        if (fetchError.name !== "AbortError") setError(fetchError.message);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, station?.current_song?.id, station?.playback_revision]);

  // Sync volume from station status when user is not actively dragging slider
  useEffect(() => {
    if (station?.volume !== undefined && !isChangingVolumeRef.current) {
      setLocalVolume(station.volume);
    }
  }, [station?.volume]);

  useEffect(() => {
    const player = audioRef.current;
    if (!player || !audioUrl) return;
    if (!isChangingVolumeRef.current) {
      player.volume = Math.max(0, Math.min(1, localVolume / 100));
      player.muted = localVolume === 0;
    }
    if (station?.status === "playing")
      void player.play().catch(() => setError("Click the audio player once to allow sound in this browser."));
    if (station?.status === "paused" || station?.status === "stopped") player.pause();
  }, [audioUrl, station?.status]);

  const title = useMemo(
    () => (station?.current_song ? `${station.current_song.title} — ${station.current_song.artist}` : "No track on air"),
    [station]
  );

  const filteredSongs = useMemo(() => {
    if (!quickFilter.trim()) return songs;
    const q = quickFilter.toLowerCase();
    return songs.filter((s) => s.title.toLowerCase().includes(q) || s.artist.toLowerCase().includes(q));
  }, [songs, quickFilter]);

  const invoke = async (path: string, init?: RequestInit) => {
    try {
      setError("");
      await request(path, token!, init);
      await refresh();
    } catch (invokeError) {
      setError(invokeError instanceof Error ? invokeError.message : "Request failed");
    }
  };

  const login = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      const result = await request("/auth/login", "", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      localStorage.setItem("radiopilot_token", result.access_token);
      setToken(result.access_token);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleVolumeChange = (value: number) => {
    isChangingVolumeRef.current = true;
    setLocalVolume(value);
    if (value > 0) setLastVolume(value);

    // Instant zero-latency hardware volume adjustment
    if (audioRef.current) {
      audioRef.current.volume = value / 100;
      audioRef.current.muted = value === 0;
    }

    // Debounce backend sync so continuous dragging doesn't freeze the UI with HTTP requests
    if (volumeDebounceTimerRef.current) {
      clearTimeout(volumeDebounceTimerRef.current);
    }
    volumeDebounceTimerRef.current = setTimeout(() => {
      isChangingVolumeRef.current = false;
      if (token) {
        void request("/station/volume", token, {
          method: "PUT",
          body: JSON.stringify({ volume: value }),
        })
          .then(() => {
            setStation((prev) => (prev ? { ...prev, volume: value } : null));
          })
          .catch(() => undefined);
      }
    }, 120);
  };

  const handleVolumeCommit = () => {
    if (volumeDebounceTimerRef.current) {
      clearTimeout(volumeDebounceTimerRef.current);
      volumeDebounceTimerRef.current = null;
    }
    isChangingVolumeRef.current = false;
    if (token) {
      void request("/station/volume", token, {
        method: "PUT",
        body: JSON.stringify({ volume: localVolume }),
      })
        .then(() => {
          setStation((prev) => (prev ? { ...prev, volume: localVolume } : null));
        })
        .catch(() => undefined);
    }
  };

  const toggleMute = () => {
    const current = localVolume;
    let target = 0;
    if (current > 0) {
      setLastVolume(current);
      target = 0;
    } else {
      target = lastVolume > 0 ? lastVolume : 75;
    }
    setLocalVolume(target);
    if (audioRef.current) {
      audioRef.current.volume = target / 100;
      audioRef.current.muted = target === 0;
    }
    if (volumeDebounceTimerRef.current) {
      clearTimeout(volumeDebounceTimerRef.current);
      volumeDebounceTimerRef.current = null;
    }
    isChangingVolumeRef.current = false;
    if (token) {
      void request("/station/volume", token, {
        method: "PUT",
        body: JSON.stringify({ volume: target }),
      })
        .then(() => {
          setStation((prev) => (prev ? { ...prev, volume: target } : null));
        })
        .catch(() => undefined);
    }
  };

  const deleteSong = async (song: Song) => {
    if (!window.confirm(`Delete ${song.title} from the library?`)) return;
    await invoke(`/library/songs/${song.id}`, { method: "DELETE" });
  };

  const clearQueue = async () => {
    if (!station?.queue.length) return;
    if (!window.confirm(`Clear all ${station.queue.length} track(s) from the live queue?`)) return;
    await invoke("/station/queue", { method: "DELETE" });
  };

  const deleteAllSongs = async () => {
    if (!songs.length) return;
    if (
      !window.confirm(
        `Delete ALL ${songs.length} song(s) from the music library? This will also remove them from every playlist and clear the live queue.`
      )
    )
      return;
    await invoke("/library/songs", { method: "DELETE" });
  };

  if (!token)
    return (
      <main className="relative grid min-h-screen place-items-center p-6 overflow-hidden">
        {/* Floating 3D Liquid Light Orbs (Apple-grade organic refraction) */}
        <div className="pointer-events-none fixed inset-0 overflow-hidden z-0 select-none">
          <div className="liquid-orb-cyan absolute -top-24 -left-24 h-96 w-96 rounded-full opacity-60" />
          <div className="liquid-orb-coral absolute top-1/3 -right-28 h-[28rem] w-[28rem] rounded-full opacity-50" />
          <div className="liquid-orb-vermilion absolute -bottom-32 left-1/4 h-96 w-96 rounded-full opacity-45" />
          <div className="liquid-orb-cream absolute top-2/3 right-1/3 h-80 w-80 rounded-full opacity-40" />
        </div>

        <form onSubmit={login} className="panel panel-floating login-card relative z-10 w-full max-w-md space-y-6 p-8">
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#00CEC8] text-[#032023] shadow-lg shadow-[#00CEC8]/25">
              <Radio size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-extrabold text-white tracking-tight">RadioPilot AI</h1>
              <p className="text-xs text-slate-400">Hybrid FM Broadcast & Automation</p>
            </div>
          </div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
            Operator Email
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="glass-input mt-2 w-full p-3 text-sm text-white focus:outline-none"
              type="email"
            />
          </label>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
            Password
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="glass-input mt-2 w-full p-3 text-sm text-white focus:outline-none"
              type="password"
            />
          </label>
          {error && <p className="text-xs text-rose-400">{error}</p>}
          <button
            disabled={loading}
            className="w-full rounded-xl bg-[#00CEC8] hover:bg-[#00b5af] py-3.5 text-sm font-bold text-[#032023] shadow-lg shadow-[#00CEC8]/30 transition"
          >
            {loading ? "Signing in..." : "Enter Station Control"}
          </button>
        </form>
      </main>
    );

  return (
    <main className="relative min-h-screen p-4 md:p-8 overflow-x-hidden">
      {/* Floating 3D Liquid Light Orbs (Refract dynamically through acrylic glassmorphism) */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden z-0 select-none">
        <div className="liquid-orb-cyan absolute -top-32 -left-20 h-[34rem] w-[34rem] rounded-full opacity-50" />
        <div className="liquid-orb-coral absolute top-1/4 -right-24 h-[30rem] w-[30rem] rounded-full opacity-45" />
        <div className="liquid-orb-vermilion absolute bottom-10 left-1/3 h-[32rem] w-[32rem] rounded-full opacity-40" />
        <div className="liquid-orb-cream absolute top-2/3 -left-16 h-88 w-88 rounded-full opacity-35" />
      </div>

      <div className="relative z-10">
        {/* Floating Capsule Header (Exact homage to reference image top bar) */}
        <header className="mx-auto mb-7 flex max-w-7xl flex-wrap items-center justify-between gap-4">
        {/* Left: Round Search / Brand Icon Capsule */}
        <div className="flex items-center gap-3">
          <div className="glass-capsule-bar grid h-11 w-11 place-items-center rounded-full text-white">
            <Radio size={20} className="text-[#00CEC8]" />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-base font-bold text-white tracking-wide">RadioPilot AI</h1>
            <p className="text-[11px] text-slate-400">FM Broadcast Ops Center</p>
          </div>
        </div>

        {/* Center: The Signature Floating Capsule Nav Bar from Reference Image */}
        <nav className="glass-capsule-bar flex items-center gap-1 p-1.5 text-xs">
          <button
            onClick={() => handleNav("dashboard")}
            className={`glass-capsule-btn ${navSection === "dashboard" ? "glass-capsule-btn-active" : ""}`}
          >
            Dashboard
          </button>
          <button
            onClick={() => handleNav("library")}
            className={`glass-capsule-btn ${navSection === "library" ? "glass-capsule-btn-active" : ""}`}
          >
            Library
          </button>
          <button
            onClick={() => handleNav("playlists")}
            className={`glass-capsule-btn ${navSection === "playlists" ? "glass-capsule-btn-active" : ""}`}
          >
            Playlists
          </button>
          <button
            onClick={() => handleNav("scheduler")}
            className={`glass-capsule-btn ${navSection === "scheduler" ? "glass-capsule-btn-active" : ""}`}
          >
            Scheduler
          </button>
          <button
            onClick={() => handleNav("ai")}
            className={`glass-capsule-btn ${navSection === "ai" ? "glass-capsule-btn-active" : ""}`}
          >
            AI Studio
          </button>
        </nav>

        {/* Right: Operator Profile Capsule */}
        <div className="flex items-center gap-2">
          <div className="glass-capsule-bar flex items-center gap-2 px-3 py-1.5 text-xs">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#EB4203] opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[#EB4203]"></span>
            </span>
            <span className="font-semibold text-slate-200">On Air</span>
            <span className="text-slate-600">|</span>
            <span className="max-w-[120px] truncate text-slate-400">admin</span>
          </div>
          <button
            onClick={() => {
              localStorage.removeItem("radiopilot_token");
              setToken(null);
            }}
            className="glass-capsule-bar grid h-9 w-9 place-items-center rounded-full text-slate-400 hover:text-white transition"
            title="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-5">
          {/* NOW PLAYING / ACTIVITY PANEL (Styled after the reference card with 3D liquid float) */}
          <section className="panel panel-floating p-6">
            <div className="flex items-center justify-between">
              <span
                className={
                  station?.status === "playing"
                    ? "badge-vermilion pulse-live"
                    : "badge-coral"
                }
              >
                ● {station?.status === "playing" ? "LIVE ON AIR" : (station?.status?.toUpperCase() ?? "STANDBY")}
              </span>
              <button
                aria-label="Toggle autopilot"
                onClick={() =>
                  void invoke(station?.mode === "AUTOPILOT" ? "/ai/autopilot/stop" : "/ai/autopilot/start", {
                    method: "POST",
                  })
                }
                className={
                  station?.mode === "AUTOPILOT"
                    ? "badge-turquoise"
                    : "badge-cream"
                }
              >
                <WandSparkles size={13} />
                {station?.mode === "AUTOPILOT" ? "AUTOPILOT ACTIVE" : "MANUAL MODE"}
              </button>
            </div>

            {/* Title Section */}
            <div className="mt-8">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Now Playing</p>
              <h2 className="mt-1 text-2xl md:text-3xl font-extrabold text-white tracking-tight">{title}</h2>
            </div>

            {/* Tri-color Progress Bar (Harmonized 4-Color Palette: #00CEC8, #FF9C5F, #FCEFC3) */}
            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>{Math.floor(station?.current_position_seconds ?? 0)}s elapsed</span>
                <span>{station?.current_song?.duration_seconds ? formatDuration(station.current_song.duration_seconds) : "Continuous Broadcast"}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-white/10 flex">
                <div
                  className="h-full bg-[#00CEC8] transition-all"
                  style={{
                    width: `${Math.min(100, Math.max(12, ((station?.current_position_seconds ?? 0) / (station?.current_song?.duration_seconds || 180)) * 100))}%`,
                  }}
                />
                <div className="h-full bg-[#FF9C5F] w-12 shrink-0 opacity-80" />
                <div className="h-full bg-[#FCEFC3] flex-1 opacity-40" />
              </div>
            </div>

            {/* 3 Circular/Squircle Stat Widgets (Direct homage to 8 In Progress / 12 Completed / 14 Up Coming from reference image) */}
            <div className="mt-6 grid grid-cols-3 gap-3">
              <div className="glass-subcard flex flex-col items-center justify-center p-3 text-center">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#00CEC8] text-[#032023] font-bold shadow-md shadow-[#00CEC8]/25">
                  <ListMusic size={18} />
                </div>
                <span className="mt-2 text-xl font-extrabold text-white">{station?.queue.length ?? 0}</span>
                <span className="text-[11px] text-slate-400">In Live Queue</span>
              </div>
              <div className="glass-subcard flex flex-col items-center justify-center p-3 text-center">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#FF9C5F] text-[#2b1102] font-bold shadow-md shadow-[#FF9C5F]/25">
                  <Music2 size={18} />
                </div>
                <span className="mt-2 text-xl font-extrabold text-white">{songs.length}</span>
                <span className="text-[11px] text-slate-400">Library Tracks</span>
              </div>
              <div className="glass-subcard flex flex-col items-center justify-center p-3 text-center">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#FCEFC3] text-[#211802] font-bold shadow-md shadow-[#FCEFC3]/25">
                  <Radio size={18} />
                </div>
                <span className="mt-2 text-xl font-extrabold text-white">{localVolume}%</span>
                <span className="text-[11px] text-slate-400">Master Level</span>
              </div>
            </div>

            {audioUrl && (
              <div className="mt-5">
                <GlassAudioPlayer
                  audioRef={audioRef}
                  audioUrl={audioUrl}
                  isPlaying={station?.status === "playing"}
                  onTogglePlay={() =>
                    void invoke(
                      station?.status === "playing"
                        ? "/station/pause"
                        : station?.status === "paused"
                        ? "/station/resume"
                        : "/station/play",
                      { method: "POST" }
                    )
                  }
                  onEnded={() =>
                    void invoke("/station/track-ended", {
                      method: "POST",
                      body: JSON.stringify({ playback_revision: station?.playback_revision }),
                    })
                  }
                  currentSong={station?.current_song}
                />
              </div>
            )}

            {/* Playback Controls (Crisp white circle button matching reference image white bar) */}
            <div className="mt-7 flex items-center gap-4">
              <button
                onClick={() =>
                  void invoke(
                    station?.status === "playing"
                      ? "/station/pause"
                      : station?.status === "paused"
                      ? "/station/resume"
                      : "/station/play",
                    { method: "POST" }
                  )
                }
                className="grid h-14 w-14 place-items-center rounded-full bg-white text-slate-950 shadow-xl shadow-white/20 hover:scale-105 transition"
                title={station?.status === "playing" ? "Pause playback" : "Start playback"}
              >
                {station?.status === "playing" ? <Pause size={24} /> : <Play size={24} className="ml-1" />}
              </button>
              <button
                onClick={() => void invoke("/station/skip", { method: "POST" })}
                className="glass-subcard grid h-14 w-14 place-items-center text-slate-300 hover:text-white"
                title="Skip to next track"
              >
                <SkipForward size={20} />
              </button>
              <div className="ml-2 flex flex-1 items-center gap-3">
                <button
                  type="button"
                  onClick={toggleMute}
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5 text-slate-300 hover:text-white hover:border-white/20 hover:bg-white/10 transition cursor-pointer backdrop-blur-md shadow-sm active:scale-95"
                  title={localVolume === 0 ? "Unmute audio (Click to restore)" : "Mute audio (Click to mute)"}
                  aria-label={localVolume === 0 ? "Unmute audio" : "Mute audio"}
                >
                  {localVolume === 0 ? (
                    <VolumeX size={19} className="text-[#EB4203] animate-in zoom-in-75 duration-150" />
                  ) : localVolume < 40 ? (
                    <Volume1 size={19} className="text-slate-300 hover:text-[#00CEC8] transition" />
                  ) : (
                    <Volume2 size={19} className="text-slate-300 hover:text-[#00CEC8] transition" />
                  )}
                </button>
                <input
                  aria-label="Volume"
                  value={localVolume}
                  type="range"
                  min="0"
                  max="100"
                  className="w-full accent-[#00CEC8] cursor-pointer touch-none"
                  onInput={(e) => handleVolumeChange(Number(e.currentTarget.value))}
                  onChange={(e) => handleVolumeChange(Number(e.currentTarget.value))}
                  onPointerUp={handleVolumeCommit}
                  onMouseUp={handleVolumeCommit}
                  onTouchEnd={handleVolumeCommit}
                />
                <span className="font-mono text-sm text-slate-300 w-8 text-right shrink-0">
                  {localVolume}
                </span>
              </div>
            </div>
          </section>

          {/* LIVE QUEUE PANEL (3D liquid float delayed) */}
          <section className="panel panel-floating-delayed p-6">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ListMusic size={19} className="text-[#00CEC8]" />
                <h2 className="font-bold text-white">Live queue</h2>
                {Boolean(station?.queue.length) && (
                  <span className="badge-turquoise text-[11px] py-0.5 px-2">
                    {station?.queue.length}
                  </span>
                )}
              </div>
              {Boolean(station?.queue.length) && (
                <button
                  onClick={() => void clearQueue()}
                  className="flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/15 px-2.5 py-1 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/25"
                >
                  <Trash2 size={13} /> Clear queue
                </button>
              )}
            </div>
            {station?.queue.length ? (
              <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
                {station.queue.map((song, i) => (
                  <div
                    key={`${song.id}-${i}`}
                    className="glass-subcard flex items-center gap-3 px-3.5 py-2.5 text-xs"
                  >
                    <span className="w-5 text-center font-mono font-bold text-[#00CEC8]">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-slate-200">{song.title}</p>
                      <p className="truncate text-[11px] text-slate-400">{song.artist}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted text-sm">Add a song from the library to begin.</p>
            )}
          </section>

          {/* AI CONSOLE */}
          <div id="ai-console-section">
            <AIConsole token={token} />
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <aside className="space-y-5">
          <div id="operations-section" className="relative z-30">
            <OperationsWorkspace
              token={token}
              songs={songs}
              refresh={async () => refresh()}
              activeTab={operationsTab}
              onTabChange={(t) => {
                setOperationsTab(t);
                if (t === "library" || t === "playlists" || t === "scheduler") {
                  setNavSection(t);
                }
              }}
            />
          </div>

          {/* QUICK QUEUE PANEL */}
          <section className="panel p-5 relative z-10">
            <div className="flex items-center justify-between gap-2 pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <h2 className="font-bold text-sm text-slate-100">Quick queue</h2>
                <span className="glass-capsule px-2.5 py-0.5 text-[11px] font-medium text-slate-300">
                  {quickFilter ? `${filteredSongs.length}/${songs.length}` : songs.length}
                </span>
              </div>
              {songs.length > 0 && (
                <button
                  onClick={() => void deleteAllSongs()}
                  className="flex items-center gap-1 rounded-lg bg-rose-500/10 border border-rose-500/25 px-2 py-1 text-[11px] font-semibold text-rose-300 hover:bg-rose-500/20 transition"
                  title="Delete all songs from library"
                >
                  <Trash2 size={12} /> Delete all
                </button>
              )}
            </div>

            {/* Quick search/filter input when there are songs */}
            {songs.length > 3 && (
              <div className="mt-3 relative">
                <Search size={13} className="absolute left-3 top-2.5 text-slate-400 pointer-events-none" />
                <input
                  value={quickFilter}
                  onChange={(e) => setQuickFilter(e.target.value)}
                  placeholder="Filter songs by title or artist..."
                  className="glass-input w-full py-1.5 pl-8 pr-7 text-xs text-slate-200 placeholder-slate-500 focus:outline-none"
                />
                {quickFilter && (
                  <button
                    onClick={() => setQuickFilter("")}
                    className="absolute right-2.5 top-2 text-slate-500 hover:text-slate-300"
                    title="Clear filter"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            )}

            {/* Compact scrollable list of tracks (Styled with dark glass cards) */}
            <div className="mt-3 max-h-[380px] space-y-2 overflow-y-auto pr-1">
              {filteredSongs.map((song) => {
                const duration = formatDuration(song.duration_seconds);
                return (
                  <div
                    key={song.id}
                    className="glass-subcard group flex items-center justify-between gap-2 p-2.5"
                  >
                    <button
                      onClick={() =>
                        void invoke("/station/queue", {
                          method: "POST",
                          body: JSON.stringify({ song_id: song.id }),
                        })
                      }
                      className="min-w-0 flex-1 text-left"
                      title={`Click to queue ${song.title}`}
                    >
                      <p className="truncate text-xs font-medium text-slate-200 group-hover:text-[#00CEC8] transition">
                        {song.title}
                      </p>
                      <div className="flex items-center gap-2 text-[11px] text-slate-400">
                        <span className="truncate">{song.artist}</span>
                        {duration && <span className="shrink-0 text-[10px] text-slate-500">{duration}</span>}
                      </div>
                    </button>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() =>
                          void invoke("/station/queue", {
                            method: "POST",
                            body: JSON.stringify({ song_id: song.id }),
                          })
                        }
                        className="rounded-lg p-1.5 text-slate-400 opacity-70 group-hover:opacity-100 hover:bg-[#00CEC8]/20 hover:text-[#00CEC8] transition"
                        title="Add to live queue"
                      >
                        <Plus size={14} />
                      </button>
                      <button
                        onClick={() => void deleteSong(song)}
                        aria-label={`Delete ${song.title}`}
                        className="rounded-lg p-1.5 text-slate-400 opacity-70 group-hover:opacity-100 hover:bg-rose-500/20 hover:text-rose-300 transition"
                        title="Delete song"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                );
              })}

              {!songs.length && (
                <p className="muted py-4 text-center text-xs">Upload a song in the Library tab first.</p>
              )}

              {songs.length > 0 && !filteredSongs.length && (
                <p className="muted py-4 text-center text-xs">No songs match &ldquo;{quickFilter}&rdquo;</p>
              )}
            </div>

            {error && <p className="mt-3 text-xs text-rose-400">{error}</p>}
          </section>
        </aside>
      </section>
      </div>
    </main>
  );
}
