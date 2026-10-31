"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { CalendarClock, FolderOpen, ListPlus, Music2, Trash2, Upload, X } from "lucide-react";
import GlassSelect from "./GlassSelect";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Song = { id: number; title: string; artist: string };
type Playlist = { id: number; name: string; description?: string };
type PlaylistDetail = Playlist & { songs: Song[] };
type Schedule = { id: number; name: string; event_type: string; playlist_id?: number; run_at: string; enabled: boolean };
type Props = {
  token: string;
  songs: Song[];
  refresh: () => Promise<void>;
  activeTab?: "library" | "playlists" | "scheduler" | "logs";
  onTabChange?: (tab: "library" | "playlists" | "scheduler" | "logs") => void;
};

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

async function api(path: string, token: string, init: RequestInit = {}) {
  const response = await fetch(`${API}${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, ...init.headers } });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const errorMsg = formatApiError(data?.detail ?? response.statusText);
    throw new Error(errorMsg);
  }
  return data;
}

export default function OperationsWorkspace({ token, songs, refresh, activeTab, onTabChange }: Props) {
  const [internalTab, setInternalTab] = useState<"library" | "playlists" | "scheduler" | "logs">("library");
  const tab = activeTab ?? internalTab;
  const setTab = (newTab: "library" | "playlists" | "scheduler" | "logs") => {
    setInternalTab(newTab);
    onTabChange?.(newTab);
  };
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [history, setHistory] = useState<Array<{ id: number; task_type: string; status: string; agent: string }>>([]);
  const [notice, setNotice] = useState("");
  const [uploads, setUploads] = useState<File[]>([]);
  const [playlistName, setPlaylistName] = useState("");
  const [selectedPlaylist, setSelectedPlaylist] = useState("");
  const [selectedSong, setSelectedSong] = useState("");
  const [openedPlaylist, setOpenedPlaylist] = useState<PlaylistDetail | null>(null);
  const [scheduleName, setScheduleName] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [scheduleType, setScheduleType] = useState<"playlist" | "news">("playlist");
  const [newsPrepMinutes, setNewsPrepMinutes] = useState(10);
  const [newsDuration, setNewsDuration] = useState(60);

  const load = async () => {
    try {
      const [playlistData, scheduleData, historyData] = await Promise.all([
        api("/playlists", token),
        api("/schedules?upcoming=false", token),
        api("/ai/history", token),
      ]);
      setPlaylists(playlistData);
      setSchedules(scheduleData);
      setHistory(historyData);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load operational data");
    }
  };

  useEffect(() => { void load(); }, [token]);

  // Synchronize immediately when Nova or other components execute actions
  useEffect(() => {
    const handleRefresh = () => { void load(); };
    window.addEventListener("station-refresh", handleRefresh);
    return () => window.removeEventListener("station-refresh", handleRefresh);
  }, [token]);

  // Reload when switching tabs so newly created playlists or schedules appear instantly
  useEffect(() => { void load(); }, [tab]);

  const selectFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = Array.from(event.target.files ?? []);
    const audioExts = [".mp3", ".wav", ".ogg", ".mp4", ".m4a", ".aac", ".flac"];
    const isAudio = (f: File) => f.type.startsWith("audio/") || audioExts.some(ext => f.name.toLowerCase().endsWith(ext));
    const valid = chosen.filter(isAudio);
    const skipped = chosen.length - valid.length;
    setUploads(valid);
    if (skipped > 0 && valid.length > 0) {
      setNotice(`Filtered out ${skipped} non-audio/shortcut file(s) (e.g. .lnk). ${valid.length} music track(s) ready.`);
    } else if (skipped > 0 && valid.length === 0) {
      setNotice("Selected file(s) are shortcuts or non-audio files. Please choose actual audio files (MP3, WAV, OGG, M4A).");
    }
  };
  const submitUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!uploads.length) return setNotice("Choose one or more audio files first.");
    const form = new FormData(); uploads.forEach(file => form.append("files", file));
    try {
      const result = await api("/library/songs/batch", token, { method: "POST", body: form });
      const uploaded: Song[] = Array.isArray(result) ? result : (result?.uploaded ?? []);
      const duplicates: string[] = Array.isArray(result) ? [] : (result?.duplicates ?? []);
      if (uploaded.length > 0 && duplicates.length > 0) {
        setNotice(`${uploaded.length} song(s) uploaded. Skipped already present: ${duplicates.join(", ")}`);
      } else if (uploaded.length > 0) {
        setNotice(`${uploaded.length} song(s) uploaded and detected.`);
      } else if (duplicates.length > 0) {
        setNotice(`Already present in library: ${duplicates.join(", ")}`);
      }
      setUploads([]);
      await refresh();
    }
    catch (error) { setNotice(error instanceof Error ? error.message : "Upload failed"); }
  };
  const deleteSong = async (song: Song) => {
    if (!window.confirm(`Delete ${song.title} from the music library and every playlist?`)) return;
    try { await api(`/library/songs/${song.id}`, token, { method: "DELETE" }); setNotice(`Deleted: ${song.title}`); if (openedPlaylist) await openPlaylist(openedPlaylist.id); await refresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not delete song"); }
  };
  const deleteAllSongs = async () => {
    if (!songs.length) return setNotice("Library is already empty.");
    if (!window.confirm(`Delete ALL ${songs.length} song(s) from the music library? This will also remove them from every playlist and clear the live queue.`)) return;
    try {
      const result = await api("/library/songs", token, { method: "DELETE" });
      setNotice(`Deleted all ${result?.deleted ?? songs.length} song(s) from library.`);
      if (openedPlaylist) await openPlaylist(openedPlaylist.id);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not delete all songs");
    }
  };
  const openPlaylist = async (playlistId: number) => {
    try { setOpenedPlaylist(await api(`/playlists/${playlistId}`, token)); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not open playlist"); }
  };
  const deletePlaylist = async (playlist: Playlist) => {
    if (!window.confirm(`Delete playlist “${playlist.name}”? Scheduled events using it will be disabled.`)) return;
    try { await api(`/playlists/${playlist.id}`, token, { method: "DELETE" }); setNotice(`Deleted playlist: ${playlist.name}`); if (openedPlaylist?.id === playlist.id) setOpenedPlaylist(null); if (selectedPlaylist === String(playlist.id)) setSelectedPlaylist(""); await load(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not delete playlist"); }
  };
  const createPlaylist = async (event: FormEvent) => {
    event.preventDefault();
    const name = playlistName.trim();
    if (!name) {
      setNotice("Please enter a playlist name first.");
      return;
    }
    try {
      await api("/playlists", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      setPlaylistName("");
      setNotice(`Playlist “${name}” created successfully.`);
      await load();
      window.dispatchEvent(new Event("station-refresh"));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not create playlist");
    }
  };
  const addSong = async () => {
    if (!selectedPlaylist || !selectedSong) return setNotice("Choose a playlist and song first.");
    try { await api(`/playlists/${selectedPlaylist}/songs/${selectedSong}`, token, { method: "POST" }); setNotice("Song added to playlist."); await openPlaylist(Number(selectedPlaylist)); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not add song"); }
  };
  const createSchedule = async (event: FormEvent) => {
    event.preventDefault();
    if (!scheduleTime || (scheduleType === "playlist" && !selectedPlaylist)) return setNotice(scheduleType === "news" ? "Choose the news broadcast date/time." : "Choose a playlist and date/time.");
    try {
      const scheduledDt = new Date(scheduleTime);
      await api("/schedules", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: scheduleName || (scheduleType === "news" ? "Autopilot news bulletin" : "Scheduled playlist"),
          event_type: scheduleType,
          playlist_id: scheduleType === "playlist" ? Number(selectedPlaylist) : null,
          run_at: scheduledDt.toISOString(),
          enabled: true,
          metadata_json: scheduleType === "news" ? { preparation_minutes: newsPrepMinutes, duration_seconds: newsDuration, mix: ["headlines", "weather", "station"] } : {},
        }),
      });
      const localFormatted = scheduledDt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      setNotice(scheduleType === "news" ? `News will prepare ${newsPrepMinutes} minutes early and trigger at ${localFormatted}.` : `Playlist scheduled for ${localFormatted}.`);
      setScheduleName("");
      setScheduleTime("");
      await load();
      window.dispatchEvent(new Event("station-refresh"));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not create schedule");
    }
  };

  const deleteSchedule = async (schedule: Schedule) => {
    if (!window.confirm(`Delete scheduled ${schedule.event_type} “${schedule.name}”?`)) return;
    try {
      await api(`/schedules/${schedule.id}`, token, { method: "DELETE" });
      setNotice(`Deleted schedule: ${schedule.name}`);
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not delete schedule");
    }
  };

  const clearPastSchedules = async () => {
    if (!window.confirm("Purge all past / finished scheduled events from the database?")) return;
    try {
      const result = await api("/schedules/cleanup/past", token, { method: "DELETE" });
      setNotice(`Cleaned up ${result?.deleted ?? 0} past / finished schedule(s).`);
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not cleanup past schedules");
    }
  };

  const tabs = [{ id: "library", label: "Library" }, { id: "playlists", label: "Playlists" }, { id: "scheduler", label: "Scheduler" }, { id: "logs", label: "AI Logs" }] as const;

  // Filter only upcoming broadcasts (active and not yet passed)
  const nowMs = Date.now();
  const upcomingSchedules = schedules
    .filter((s) => s.enabled && new Date(s.run_at).getTime() >= nowMs - 5 * 60 * 1000)
    .sort((a, b) => new Date(a.run_at).getTime() - new Date(b.run_at).getTime());
  const pastCount = schedules.filter((s) => !s.enabled || new Date(s.run_at).getTime() < nowMs - 5 * 60 * 1000).length;

  return <section className="panel p-6 relative z-20">
    <div className="glass-capsule-bar inline-flex items-center gap-1 p-1">{tabs.map(item => <button key={item.id} onClick={() => setTab(item.id)} className={`glass-capsule-btn ${tab === item.id ? "glass-capsule-btn-active" : ""}`}>{item.label}</button>)}</div>
    {notice && (
      <div className="liquid-popup mt-3 flex items-center justify-between gap-3 rounded-full px-5 py-2.5 text-xs text-white shadow-lg">
        <div className="flex items-center gap-2.5 min-w-0 z-10">
          <span className="h-2 w-2 rounded-full bg-[#FF9C5F] shrink-0 shadow-sm shadow-[#FF9C5F]" />
          <span className="truncate font-medium">{notice}</span>
        </div>
        <button
          type="button"
          onClick={() => setNotice("")}
          className="text-slate-300 hover:text-white transition shrink-0 p-1 rounded-full hover:bg-white/20 z-10 active:scale-90"
          title="Dismiss message"
        >
          <X size={14} />
        </button>
      </div>
    )}
    {tab === "library" && <div className="mt-5 space-y-4"><div className="flex items-center justify-between"><div className="flex items-center gap-2"><Upload size={18} className="text-[#00CEC8]"/><h2 className="font-bold text-white">Upload music</h2></div>{songs.length > 0 && <button type="button" onClick={() => void deleteAllSongs()} className="flex items-center gap-1.5 rounded-lg border border-rose-500/25 bg-rose-500/15 px-2.5 py-1 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/25"><Trash2 size={13}/> Delete all songs</button>}</div><form onSubmit={submitUpload} className="space-y-3"><label className="block cursor-pointer rounded-2xl border-2 border-dashed border-[#00CEC8]/40 bg-[#00CEC8]/5 backdrop-blur-md p-6 text-center transition hover:border-[#00CEC8]/70 hover:bg-[#00CEC8]/10"><Upload className="mx-auto mb-2 text-[#00CEC8]" size={28}/><span className="block font-semibold text-slate-100">Choose multiple music files</span><span className="muted mt-1 block text-xs">MP3, WAV, OGG, M4A or FLAC · Select up to 50 songs</span><input type="file" multiple accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/aac,audio/flac,.mp3,.wav,.ogg,.m4a,.aac,.flac" onChange={selectFiles} className="sr-only"/></label>{uploads.length > 0 && <p className="text-xs text-[#00CEC8] font-medium">{uploads.length} file(s) selected: {uploads.slice(0, 3).map(file => file.name).join(", ")}{uploads.length > 3 ? "…" : ""}</p>}<button className="rounded-xl bg-[#00CEC8] hover:bg-[#00b5af] px-4 py-2.5 text-sm font-bold text-[#032023] shadow-md shadow-[#00CEC8]/25 transition">Upload selected songs</button></form><div className="flex items-center justify-between text-xs"><p className="muted">Song title and artist are detected automatically.</p>{songs.length > 0 && <span className="muted font-medium">{songs.length} song(s)</span>}</div><div className="max-h-56 space-y-2 overflow-auto pr-1">{songs.length ? songs.map(song => <div key={song.id} className="glass-subcard flex items-center justify-between p-2.5 text-xs"><span><b className="text-white">{song.title}</b> <span className="muted">— {song.artist}</span></span><button onClick={() => void deleteSong(song)} aria-label={`Delete ${song.title}`} className="rounded-lg p-1 text-rose-300 hover:bg-rose-500/20"><Trash2 size={15}/></button></div>) : <p className="muted py-2 text-center text-xs">Library has no songs.</p>}</div></div>}
    {tab === "playlists" && <div className="mt-5 space-y-4">
      <div className="flex items-center gap-2"><Music2 size={18} className="text-[#FF9C5F]"/><h2 className="font-bold text-white">Playlists</h2></div>
      <form onSubmit={createPlaylist} className="flex gap-2">
        <input value={playlistName} onChange={e => setPlaylistName(e.target.value)} placeholder="Playlist name" className="glass-input min-w-0 flex-1 p-2.5 text-sm text-white focus:outline-none"/>
        <button className="rounded-xl bg-[#00CEC8] hover:bg-[#00b5af] px-4 text-sm font-bold text-[#032023] shadow-md shadow-[#00CEC8]/25 transition">Create</button>
      </form>
      <div className="space-y-2">
        {playlists.map(playlist => (
          <div key={playlist.id} className="glass-subcard flex items-center justify-between p-2">
            <button onClick={() => void openPlaylist(playlist.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs text-slate-200 hover:text-white transition">
              <FolderOpen size={15} className="text-[#FF9C5F]"/>
              <span className="truncate font-medium">{playlist.name}</span>
            </button>
            <button onClick={() => void deletePlaylist(playlist)} aria-label={`Delete playlist ${playlist.name}`} className="rounded-lg p-1.5 text-rose-300 hover:bg-rose-500/20">
              <Trash2 size={15}/>
            </button>
          </div>
        ))}
      </div>
      <div className="space-y-2.5 relative z-30">
        <GlassSelect
          value={selectedPlaylist}
          onChange={val => {
            setSelectedPlaylist(val);
            if (val) void openPlaylist(Number(val));
          }}
          placeholder="Choose playlist to edit"
          options={playlists.map(playlist => ({
            value: String(playlist.id),
            label: playlist.name,
          }))}
        />
        <GlassSelect
          value={selectedSong}
          onChange={val => setSelectedSong(val)}
          placeholder="Choose library song"
          options={songs.map(song => ({
            value: String(song.id),
            label: `${song.title} — ${song.artist}`,
          }))}
        />
      </div>
      <button onClick={addSong} className="flex items-center gap-2 rounded-xl bg-[#00CEC8] hover:bg-[#00b5af] px-4 py-2.5 text-sm font-bold text-[#032023] shadow-md shadow-[#00CEC8]/30 transition hover:scale-[1.02] active:scale-[0.98]">
        <ListPlus size={16} className="text-[#032023] stroke-[2.5]"/> Add song
      </button>
      {openedPlaylist && (
        <div className="glass-subcard p-4">
          <p className="mb-2 text-sm font-semibold text-white">{openedPlaylist.name} · {openedPlaylist.songs.length} songs</p>
          {openedPlaylist.songs.length ? openedPlaylist.songs.map((song, index) => (
            <p key={song.id} className="muted py-1 text-xs">{index + 1}. {song.title} — {song.artist}</p>
          )) : <p className="muted text-xs">This playlist has no songs yet.</p>}
        </div>
      )}
    </div>}
    {tab === "scheduler" && <div className="mt-5 space-y-4">
      <div className="flex items-center gap-2"><CalendarClock size={18} className="text-[#FF9C5F]"/><h2 className="font-bold text-white">Autopilot schedule</h2></div>
      <form onSubmit={createSchedule} className="space-y-3">
        <GlassSelect<"playlist" | "news">
          value={scheduleType}
          onChange={val => setScheduleType(val)}
          options={[
            { value: "playlist", label: "Playlist" },
            { value: "news", label: "1-minute news bulletin" },
          ]}
        />
        <input value={scheduleName} onChange={e => setScheduleName(e.target.value)} placeholder={scheduleType === "news" ? "News bulletin name" : "Show or event name"} className="glass-input w-full p-2.5 text-sm text-slate-200 focus:outline-none"/>
        <input value={scheduleTime} onChange={e => setScheduleTime(e.target.value)} type="datetime-local" className="glass-input w-full p-2.5 text-sm text-slate-200 focus:outline-none"/>
        {scheduleType === "playlist" ? (
          <GlassSelect
            value={selectedPlaylist}
            onChange={val => setSelectedPlaylist(val)}
            placeholder="Choose playlist"
            options={playlists.map(playlist => ({
              value: String(playlist.id),
              label: playlist.name,
            }))}
          />
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-medium">Prepare early</label>
              <GlassSelect<number>
                value={newsPrepMinutes}
                onChange={val => setNewsPrepMinutes(val)}
                options={[
                  { value: 5, label: "5 minutes" },
                  { value: 10, label: "10 minutes" },
                  { value: 15, label: "15 minutes" },
                  { value: 30, label: "30 minutes" },
                ]}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-medium">Bulletin length</label>
              <GlassSelect<number>
                value={newsDuration}
                onChange={val => setNewsDuration(val)}
                options={[
                  { value: 45, label: "45 seconds" },
                  { value: 60, label: "1 minute" },
                  { value: 90, label: "90 seconds" },
                ]}
              />
            </div>
          </div>
        )}
        <button className="rounded-xl bg-[#00CEC8] hover:bg-[#00b5af] px-4 py-2.5 text-sm font-bold text-[#032023] shadow-md shadow-[#00CEC8]/25 transition">
          Schedule {scheduleType === "news" ? "news" : "playlist"}
        </button>
      </form>
      <p className="muted text-xs">News preparation mixes verified headlines with weather and station updates. Prepared automatically before airtime.</p>

      <div className="flex items-center justify-between border-t border-white/10 pt-3 text-xs">
        <span className="font-semibold text-white">Upcoming Broadcasts ({upcomingSchedules.length})</span>
        {pastCount > 0 && (
          <button
            type="button"
            onClick={() => void clearPastSchedules()}
            className="flex items-center gap-1 rounded-lg border border-rose-500/25 bg-rose-500/15 px-2.5 py-1 text-[11px] font-semibold text-rose-300 transition hover:bg-rose-500/25"
            title="Purge all past / expired records"
          >
            <Trash2 size={12} /> Purge {pastCount} past record(s)
          </button>
        )}
      </div>

      <div className="space-y-2">
        {upcomingSchedules.length ? (
          upcomingSchedules.map(schedule => {
            const schedDate = new Date(schedule.run_at);
            const isSoon = schedDate.getTime() - nowMs < 30 * 60 * 1000 && schedDate.getTime() >= nowMs;
            return (
              <div key={schedule.id} className="glass-subcard flex items-center justify-between p-2.5 transition-all hover:border-white/20">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-xs font-semibold text-white">{schedule.name}</p>
                    {isSoon && (
                      <span className="rounded bg-[#EB4203]/20 border border-[#EB4203]/40 px-1.5 py-0.5 text-[9px] font-bold text-[#EB4203] animate-pulse">
                        ON AIR SOON
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {schedDate.toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={schedule.event_type === "news" ? "badge-coral text-[10px]" : "badge-turquoise text-[10px]"}>
                    {schedule.event_type === "news" ? "NEWS" : "PLAYLIST"}
                  </span>
                  <button
                    onClick={() => void deleteSchedule(schedule)}
                    aria-label={`Delete schedule ${schedule.name}`}
                    title="Delete scheduled event"
                    className="rounded-lg p-1.5 text-rose-300 hover:bg-rose-500/20 transition hover:text-white"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            );
          })
        ) : (
          <p className="muted py-4 text-center text-xs">No upcoming schedules. All finished broadcasts have cleared.</p>
        )}
      </div>
    </div>}
    {tab === "logs" && <div className="mt-5 space-y-2"><h2 className="font-bold text-white">Recent AI tasks</h2>{history.length ? history.slice(0, 8).map(item => <div key={item.id} className="glass-subcard flex items-center justify-between p-2.5 text-xs"><span className="font-semibold text-[#00CEC8]">{item.agent}</span><span className="text-slate-300">{item.task_type}</span><span className="badge-turquoise text-[10px]">{item.status}</span></div>) : <p className="muted text-sm">No AI tasks recorded yet.</p>}</div>}
  </section>;
}
