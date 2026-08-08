"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { CalendarClock, ListPlus, Music2, Upload } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Song = { id: number; title: string; artist: string };
type Playlist = { id: number; name: string; description?: string };
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
  const [history, setHistory] = useState<Array<{ id: number; task_type: string; status: string; agent: string; created_at: string }>>([]);
  const [notice, setNotice] = useState("");
  const [upload, setUpload] = useState<{ file: File | null; title: string; artist: string }>({ file: null, title: "", artist: "" });
  const [playlistName, setPlaylistName] = useState("");
  const [selectedPlaylist, setSelectedPlaylist] = useState("");
  const [selectedSong, setSelectedSong] = useState("");
  const [scheduleName, setScheduleName] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");

  const load = async () => {
    try {
      const [playlistData, scheduleData, historyData] = await Promise.all([api("/playlists", token), api("/schedules", token), api("/ai/history", token)]);
      setPlaylists(playlistData); setSchedules(scheduleData); setHistory(historyData);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not load operational data"); }
  };
  useEffect(() => { void load(); }, [token]);
  const submitUpload = async (event: FormEvent) => { event.preventDefault(); if (!upload.file || !upload.title.trim()) return setNotice("Choose an audio file and give it a title."); const form = new FormData(); form.append("file", upload.file); form.append("title", upload.title); form.append("artist", upload.artist || "Unknown Artist"); try { await api("/library/songs", token, { method: "POST", body: form }); setNotice("Song uploaded to the library."); setUpload({ file: null, title: "", artist: "" }); await refresh(); } catch (error) { setNotice(error instanceof Error ? error.message : "Upload failed"); } };
  const createPlaylist = async (event: FormEvent) => { event.preventDefault(); try { await api("/playlists", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: playlistName }) }); setPlaylistName(""); setNotice("Playlist created."); await load(); } catch (error) { setNotice(error instanceof Error ? error.message : "Could not create playlist"); } };
  const addSong = async () => { if (!selectedPlaylist || !selectedSong) return setNotice("Choose a playlist and song first."); try { await api(`/playlists/${selectedPlaylist}/songs/${selectedSong}`, token, { method: "POST" }); setNotice("Song added to the playlist."); } catch (error) { setNotice(error instanceof Error ? error.message : "Could not add song"); } };
  const createSchedule = async (event: FormEvent) => { event.preventDefault(); if (!selectedPlaylist || !scheduleTime) return setNotice("Choose a playlist and date/time."); try { await api("/schedules", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: scheduleName || "Scheduled playlist", event_type: "playlist", playlist_id: Number(selectedPlaylist), run_at: new Date(scheduleTime).toISOString(), enabled: true }) }); setNotice("Playlist scheduled."); setScheduleName(""); setScheduleTime(""); await load(); } catch (error) { setNotice(error instanceof Error ? error.message : "Could not create schedule"); } };
  const selectFile = (event: ChangeEvent<HTMLInputElement>) => setUpload(current => ({ ...current, file: event.target.files?.[0] ?? null }));
  const tabs = [{ id: "library", label: "Library" }, { id: "playlists", label: "Playlists" }, { id: "scheduler", label: "Scheduler" }, { id: "logs", label: "AI Logs" }] as const;
  return <section className="panel p-5"><div className="flex flex-wrap gap-2">{tabs.map(item => <button key={item.id} onClick={() => setTab(item.id)} className={`rounded-md px-3 py-2 text-xs font-semibold ${tab === item.id ? "bg-violet-500 text-white" : "bg-slate-800 text-slate-300"}`}>{item.label}</button>)}</div>{notice && <p className="mt-3 rounded-md bg-slate-950 p-2 text-xs text-amber-300">{notice}</p>}{tab === "library" && <div className="mt-5"><div className="flex items-center gap-2"><Upload size={18}/><h2 className="font-bold">Upload music</h2></div><form onSubmit={submitUpload} className="mt-3 space-y-2"><input type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4" onChange={selectFile} className="block w-full text-xs"/><input value={upload.title} onChange={e => setUpload({ ...upload, title: e.target.value })} placeholder="Song title" className="w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"/><input value={upload.artist} onChange={e => setUpload({ ...upload, artist: e.target.value })} placeholder="Artist" className="w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"/><button className="rounded-md bg-violet-500 px-3 py-2 text-sm font-semibold">Upload to library</button></form><p className="muted mt-4 text-xs">{songs.length} song(s) currently available.</p></div>}{tab === "playlists" && <div className="mt-5 space-y-3"><div className="flex items-center gap-2"><Music2 size={18}/><h2 className="font-bold">Build playlists</h2></div><form onSubmit={createPlaylist} className="flex gap-2"><input value={playlistName} onChange={e => setPlaylistName(e.target.value)} placeholder="Playlist name" className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"/><button className="rounded-md bg-violet-500 px-3 text-sm">Create</button></form><select value={selectedPlaylist} onChange={e => setSelectedPlaylist(e.target.value)} className="w-full rounded-md bg-slate-950 p-2 text-sm"><option value="">Choose playlist</option>{playlists.map(playlist => <option key={playlist.id} value={playlist.id}>{playlist.name}</option>)}</select><select value={selectedSong} onChange={e => setSelectedSong(e.target.value)} className="w-full rounded-md bg-slate-950 p-2 text-sm"><option value="">Choose song</option>{songs.map(song => <option key={song.id} value={song.id}>{song.title} — {song.artist}</option>)}</select><button onClick={addSong} className="flex items-center gap-2 rounded-md bg-slate-800 px-3 py-2 text-sm"><ListPlus size={16}/> Add song</button></div>}{tab === "scheduler" && <div className="mt-5 space-y-3"><div className="flex items-center gap-2"><CalendarClock size={18}/><h2 className="font-bold">Schedule playlist</h2></div><form onSubmit={createSchedule} className="space-y-2"><input value={scheduleName} onChange={e => setScheduleName(e.target.value)} placeholder="Show or event name" className="w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"/><input value={scheduleTime} onChange={e => setScheduleTime(e.target.value)} type="datetime-local" className="w-full rounded-md bg-slate-950 p-2 text-sm"/><select value={selectedPlaylist} onChange={e => setSelectedPlaylist(e.target.value)} className="w-full rounded-md bg-slate-950 p-2 text-sm"><option value="">Choose playlist</option>{playlists.map(playlist => <option key={playlist.id} value={playlist.id}>{playlist.name}</option>)}</select><button className="rounded-md bg-violet-500 px-3 py-2 text-sm font-semibold">Schedule</button></form><div className="space-y-1">{schedules.slice(0, 5).map(schedule => <p key={schedule.id} className="muted text-xs">{new Date(schedule.run_at).toLocaleString()} · {schedule.name}</p>)}</div></div>}{tab === "logs" && <div className="mt-5 space-y-2"><h2 className="font-bold">Recent AI tasks</h2>{history.length ? history.slice(0, 8).map(item => <div key={item.id} className="rounded-md bg-slate-950 p-2 text-xs"><span className="font-semibold">{item.agent}</span> · {item.task_type}<span className="muted float-right">{item.status}</span></div>) : <p className="muted text-sm">No AI tasks recorded yet.</p>}</div>}</section>;
}
