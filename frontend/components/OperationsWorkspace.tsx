"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { CalendarClock, FolderOpen, ListPlus, Music2, Trash2, Upload } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Song = { id: number; title: string; artist: string };
type Playlist = { id: number; name: string; description?: string };
type PlaylistDetail = Playlist & { songs: Song[] };
type Schedule = { id: number; name: string; event_type: string; playlist_id?: number; run_at: string; enabled: boolean };
type Props = { token: string; songs: Song[]; refresh: () => Promise<void> };

async function api(path: string, token: string, init: RequestInit = {}) {
  const response = await fetch(`${API}${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, ...init.headers } });
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? "Request failed");
  return data;
}

export default function OperationsWorkspace({ token, songs, refresh }: Props) {
  const [tab, setTab] = useState<"library" | "playlists" | "scheduler" | "logs">("library");
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

  const load = async () => {
    try {
      const [playlistData, scheduleData, historyData] = await Promise.all([api("/playlists", token), api("/schedules", token), api("/ai/history", token)]);
      setPlaylists(playlistData); setSchedules(scheduleData); setHistory(historyData);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not load operational data"); }
  };
  useEffect(() => { void load(); }, [token]);

  const selectFiles = (event: ChangeEvent<HTMLInputElement>) => setUploads(Array.from(event.target.files ?? []));
  const submitUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!uploads.length) return setNotice("Choose one or more audio files first.");
    const form = new FormData(); uploads.forEach(file => form.append("files", file));
    try { const uploaded: Song[] = await api("/library/songs/batch", token, { method: "POST", body: form }); setNotice(`${uploaded.length} song(s) uploaded and detected.`); setUploads([]); await refresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Upload failed"); }
  };
  const deleteSong = async (song: Song) => {
    if (!window.confirm(`Delete ${song.title} from the music library and every playlist?`)) return;
    try { await api(`/library/songs/${song.id}`, token, { method: "DELETE" }); setNotice(`Deleted: ${song.title}`); if (openedPlaylist) await openPlaylist(openedPlaylist.id); await refresh(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not delete song"); }
  };
  const openPlaylist = async (playlistId: number) => {
    try { setOpenedPlaylist(await api(`/playlists/${playlistId}`, token)); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not open playlist"); }
  };
  const createPlaylist = async (event: FormEvent) => {
    event.preventDefault();
    try { await api("/playlists", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: playlistName }) }); setPlaylistName(""); setNotice("Playlist created."); await load(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not create playlist"); }
  };
  const addSong = async () => {
    if (!selectedPlaylist || !selectedSong) return setNotice("Choose a playlist and song first.");
    try { await api(`/playlists/${selectedPlaylist}/songs/${selectedSong}`, token, { method: "POST" }); setNotice("Song added to playlist."); await openPlaylist(Number(selectedPlaylist)); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not add song"); }
  };
  const createSchedule = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedPlaylist || !scheduleTime) return setNotice("Choose a playlist and date/time.");
    try { await api("/schedules", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: scheduleName || "Scheduled playlist", event_type: "playlist", playlist_id: Number(selectedPlaylist), run_at: new Date(scheduleTime).toISOString(), enabled: true }) }); setNotice("Playlist scheduled."); setScheduleName(""); setScheduleTime(""); await load(); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Could not create schedule"); }
  };
  const tabs = [{ id: "library", label: "Library" }, { id: "playlists", label: "Playlists" }, { id: "scheduler", label: "Scheduler" }, { id: "logs", label: "AI Logs" }] as const;

  return <section className="panel p-5">
    <div className="flex flex-wrap gap-2">{tabs.map(item => <button key={item.id} onClick={() => setTab(item.id)} className={`rounded-md px-3 py-2 text-xs font-semibold ${tab === item.id ? "bg-violet-500 text-white" : "bg-slate-800 text-slate-300"}`}>{item.label}</button>)}</div>
    {notice && <p className="mt-3 rounded-md bg-slate-950 p-2 text-xs text-amber-300">{notice}</p>}
    {tab === "library" && <div className="mt-5 space-y-4"><div className="flex items-center gap-2"><Upload size={18}/><h2 className="font-bold">Upload music</h2></div><form onSubmit={submitUpload} className="space-y-3"><label className="block cursor-pointer rounded-xl border-2 border-dashed border-violet-400 bg-violet-500/10 p-5 text-center transition hover:bg-violet-500/20"><Upload className="mx-auto mb-2 text-violet-300" size={26}/><span className="block font-semibold text-violet-100">Choose multiple music files</span><span className="muted mt-1 block text-xs">MP3, WAV, OGG or M4A · Select up to 50 songs</span><input type="file" multiple accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4" onChange={selectFiles} className="sr-only"/></label>{uploads.length > 0 && <p className="text-xs text-emerald-300">{uploads.length} file(s) selected: {uploads.slice(0, 3).map(file => file.name).join(", ")}{uploads.length > 3 ? "…" : ""}</p>}<button className="rounded-md bg-violet-500 px-3 py-2 text-sm font-semibold">Upload selected songs</button></form><p className="muted text-xs">Song title and artist are detected automatically. Deleting a library song also removes it from every playlist.</p><div className="max-h-56 space-y-1 overflow-auto">{songs.map(song => <div key={song.id} className="flex items-center justify-between rounded-md bg-slate-950 p-2 text-xs"><span><b>{song.title}</b> <span className="muted">— {song.artist}</span></span><button onClick={() => void deleteSong(song)} aria-label={`Delete ${song.title}`} className="rounded p-1 text-rose-300 hover:bg-rose-500/20"><Trash2 size={15}/></button></div>)}</div></div>}
    {tab === "playlists" && <div className="mt-5 space-y-3"><div className="flex items-center gap-2"><Music2 size={18}/><h2 className="font-bold">Playlists</h2></div><form onSubmit={createPlaylist} className="flex gap-2"><input value={playlistName} onChange={e => setPlaylistName(e.target.value)} placeholder="Playlist name" className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"/><button className="rounded-md bg-violet-500 px-3 text-sm">Create</button></form><div className="flex flex-wrap gap-2">{playlists.map(playlist => <button key={playlist.id} onClick={() => void openPlaylist(playlist.id)} className="flex items-center gap-1 rounded-md bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700"><FolderOpen size={14}/>{playlist.name}</button>)}</div><select value={selectedPlaylist} onChange={e => { setSelectedPlaylist(e.target.value); if (e.target.value) void openPlaylist(Number(e.target.value)); }} className="w-full rounded-md bg-slate-950 p-2 text-sm"><option value="">Choose playlist to edit</option>{playlists.map(playlist => <option key={playlist.id} value={playlist.id}>{playlist.name}</option>)}</select><select value={selectedSong} onChange={e => setSelectedSong(e.target.value)} className="w-full rounded-md bg-slate-950 p-2 text-sm"><option value="">Choose library song</option>{songs.map(song => <option key={song.id} value={song.id}>{song.title} — {song.artist}</option>)}</select><button onClick={addSong} className="flex items-center gap-2 rounded-md bg-slate-800 px-3 py-2 text-sm"><ListPlus size={16}/> Add song</button>{openedPlaylist && <div className="rounded-lg bg-slate-950 p-3"><p className="mb-2 text-sm font-semibold">{openedPlaylist.name} · {openedPlaylist.songs.length} songs</p>{openedPlaylist.songs.length ? openedPlaylist.songs.map((song, index) => <p key={song.id} className="muted py-1 text-xs">{index + 1}. {song.title} — {song.artist}</p>) : <p className="muted text-xs">This playlist has no songs yet.</p>}</div>}</div>}
    {tab === "scheduler" && <div className="mt-5 space-y-3"><div className="flex items-center gap-2"><CalendarClock size={18}/><h2 className="font-bold">Schedule playlist</h2></div><form onSubmit={createSchedule} className="space-y-2"><input value={scheduleName} onChange={e => setScheduleName(e.target.value)} placeholder="Show or event name" className="w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"/><input value={scheduleTime} onChange={e => setScheduleTime(e.target.value)} type="datetime-local" className="w-full rounded-md bg-slate-950 p-2 text-sm"/><select value={selectedPlaylist} onChange={e => setSelectedPlaylist(e.target.value)} className="w-full rounded-md bg-slate-950 p-2 text-sm"><option value="">Choose playlist</option>{playlists.map(playlist => <option key={playlist.id} value={playlist.id}>{playlist.name}</option>)}</select><button className="rounded-md bg-violet-500 px-3 py-2 text-sm font-semibold">Schedule</button></form><div className="space-y-1">{schedules.slice(0, 5).map(schedule => <p key={schedule.id} className="muted text-xs">{new Date(schedule.run_at).toLocaleString()} · {schedule.name}</p>)}</div></div>}
    {tab === "logs" && <div className="mt-5 space-y-2"><h2 className="font-bold">Recent AI tasks</h2>{history.length ? history.slice(0, 8).map(item => <div key={item.id} className="rounded-md bg-slate-950 p-2 text-xs"><span className="font-semibold">{item.agent}</span> · {item.task_type}<span className="muted float-right">{item.status}</span></div>) : <p className="muted text-sm">No AI tasks recorded yet.</p>}</div>}
  </section>;
}
