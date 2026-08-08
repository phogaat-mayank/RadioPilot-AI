"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, LoaderCircle, Mic, Search, Sparkles, Volume2 } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type Props = { token: string };
type AIStatus = { mode: string; autopilot_enabled: boolean; pending_approvals: number };
type Discovery = { id: string; title: string; artist: string; duration_seconds: number; release_date: string | null };
type SpeechWindow = Window & { SpeechRecognition?: new () => SpeechRecognition; webkitSpeechRecognition?: new () => SpeechRecognition };
type SpeechRecognition = {
  lang: string; continuous: boolean; interimResults: boolean; maxAlternatives: number; start: () => void; abort: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null; onend: (() => void) | null;
};

export default function AIConsole({ token }: Props) {
  const [prompt, setPrompt] = useState("Create a friendly evening show intro");
  const [response, setResponse] = useState("RJ AI is ready to assist the station team.");
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Discovery[]>([]);
  const [voiceActive, setVoiceActive] = useState(false);
  const [lastHeard, setLastHeard] = useState("");
  const [voiceLanguage, setVoiceLanguage] = useState("hi-IN");
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const voiceActiveRef = useRef(false);
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoPlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const speak = (message: string) => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(message));
    }
  };

  const call = async (path: string, body?: object) => {
    setLoading(true);
    try {
      const result = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await result.json();
      if (!result.ok) throw new Error(data.detail ?? "RJ AI request failed");
      if (data.response) { setResponse(data.response); speak(data.response); }
      if (data.mode) setStatus(data);
    } catch (error) {
      setResponse(error instanceof Error ? error.message : "RJ AI request failed");
    } finally { setLoading(false); }
  };

  const findMusic = async (event: FormEvent) => {
    event.preventDefault();
    if (search.trim().length < 2) return;
    setLoading(true);
    try {
      const result = await fetch(`${API}/ai/music/search?q=${encodeURIComponent(search)}`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await result.json();
      if (!result.ok) throw new Error(data.detail ?? "Search unavailable");
      setResults(data);
    } catch (error) {
      setResponse(error instanceof Error ? error.message : "Music search failed");
    } finally { setLoading(false); }
  };

  const openYouTube = async (song: string) => {
    try {
      const result = await fetch(`${API}/ai/youtube/play-url?q=${encodeURIComponent(song)}`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await result.json();
      if (!result.ok) throw new Error(data.detail ?? "YouTube search failed");
      window.location.assign(data.url);
    } catch (error) {
      setResponse(error instanceof Error ? error.message : "YouTube redirect failed");
    }
  };

  const requestedSong = (text: string) => {
    const spoken = text.trim().replace(/[!?.,]/g, " ").replace(/\s+/g, " ");
    const match =
      spoken.match(/^(?:youtube\s+)?(?:please\s+)?(?:play|paly|plae|plaay|bajao|chalao)\s+(?:song\s+|gaana\s+)?(.+)/i) ||
      spoken.match(/(?:^|\s)(?:play|paly|plae|plaay|bajao|chalao)\s+(?:song\s+|gaana\s+)?(.+)/i) ||
      spoken.match(/^(.+?)\s+(?:chalao|chala do|bajao|baja do)$/i) ||
      spoken.match(/^(?:\u0915\u0943\u092a\u092f\u093e\s*)?(?:\u092f\u0942\u091f\u094d\u092f\u0942\u092c\s*(?:\u092a\u0930)?\s*)?(?:\u092a\u094d\u0932\u0947|\u091a\u0932\u093e\u0913|\u091a\u0932\u093e \u0926\u094b|\u092c\u091c\u093e\u0913|\u092c\u091c\u093e \u0926\u094b)\s*(?:\u0917\u093e\u0928\u093e\s*)?(.+)$/) ||
      spoken.match(/^(.+?)\s+(?:\u092a\u094d\u0932\u0947 \u0915\u0930\u094b|\u091a\u0932\u093e\u0913|\u091a\u0932\u093e \u0926\u094b|\u092c\u091c\u093e\u0913|\u092c\u091c\u093e \u0926\u094b)$/);
    const song = match?.[1]?.replace(/^(?:song|gaana|\u0917\u093e\u0928\u093e)\s+/i, "").replace(/\s+(?:song|gaana|\u0917\u093e\u0928\u093e)$/i, "").trim();
    return song && !["music", "song", "gaana", "\u0917\u093e\u0928\u093e", "\u092e\u094d\u092f\u0942\u091c\u093f\u0915"].includes(song.toLowerCase()) ? song : null;
  };

  const stopVoice = () => {
    voiceActiveRef.current = false;
    if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setVoiceActive(false);
    setLastHeard("");
    setResponse("Voice listening is OFF. Turn it on when you want to speak a command.");
  };

  const startVoice = () => {
    const Speech = (window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition;
    if (!Speech) { setResponse("Voice commands work in Chrome or Edge. Please use the text box in this browser."); return; }
    if (voiceActiveRef.current) { stopVoice(); return; }
    const recognition = new Speech();
    recognitionRef.current = recognition;
    voiceActiveRef.current = true;
    setVoiceActive(true);
    recognition.lang = voiceLanguage;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 5;
    recognition.onresult = event => {
      const alternatives = Array.from(event.results[event.results.length - 1]).map(item => item.transcript.trim());
      // Prefer an alternative containing a clear play request; otherwise use the best recognition result.
      const transcript = alternatives.find(candidate => requestedSong(candidate)) ?? alternatives[0];
      if (!transcript) return;
      setLastHeard(transcript);
      setPrompt(transcript);
      const song = requestedSong(transcript);
      if (song) {
        setResponse(`Opening ${song} on YouTube...`);
        void openYouTube(song);
      } else {
        void call("/ai/voice/command", { prompt: transcript, session_id: "voice" });
      }
    };
    recognition.onerror = () => {
      if (voiceActiveRef.current) setResponse("Microphone access was not available. Allow microphone permission and try again.");
    };
    recognition.onend = () => {
      if (!voiceActiveRef.current) return;
      restartTimerRef.current = setTimeout(() => { try { recognition.start(); } catch { /* browser is already restarting recognition */ } }, 350);
    };
    try {
      recognition.start();
      setResponse("Voice listening is ON. Say: Play Kesariya Arijit Singh.");
    } catch {
      voiceActiveRef.current = false;
      setVoiceActive(false);
      setResponse("The microphone could not start. Refresh the page, allow microphone permission, and try again.");
    }
  };

  const onPromptChange = (value: string) => {
    setPrompt(value);
    if (autoPlayTimerRef.current) clearTimeout(autoPlayTimerRef.current);
    const song = requestedSong(value);
    // A short pause prevents redirecting while the title is still being typed.
    if (song && song.length >= 4) {
      autoPlayTimerRef.current = setTimeout(() => {
        setResponse(`Opening ${song} on YouTube...`);
        void openYouTube(song);
      }, 900);
    }
  };

  useEffect(() => {
    fetch(`${API}/ai/status`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : null).then(setStatus).catch(() => undefined);
    return () => {
      voiceActiveRef.current = false;
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      if (autoPlayTimerRef.current) clearTimeout(autoPlayTimerRef.current);
      recognitionRef.current?.abort();
    };
  }, [token]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const song = requestedSong(prompt);
    if (song) void openYouTube(song); else void call("/ai/chat", { prompt, session_id: "dashboard" });
  };

  return <section className="panel p-5">
    <div className="flex items-center gap-2"><div className="rounded-lg bg-violet-500/20 p-2 text-violet-300"><Bot size={18}/></div><div><h2 className="font-bold">RJ AI Voice Studio</h2><p className="muted text-xs">Agents · voice commands · web music discovery</p></div><span className={`ml-auto pill ${status?.autopilot_enabled ? "bg-violet-500 text-white" : "bg-slate-700 text-slate-300"}`}>{status?.mode ?? "MANUAL"}</span></div>
    <form onSubmit={submit} className="mt-4 space-y-2">
      <textarea value={prompt} onChange={event => onPromptChange(event.target.value)} rows={3} className="w-full resize-none rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm" aria-label="Message RJ AI"/>
      <div className="grid grid-cols-2 gap-2"><button disabled={loading} className="flex items-center justify-center gap-2 rounded-lg bg-violet-500 py-2 text-sm font-semibold">{loading ? <LoaderCircle className="animate-spin" size={16}/> : <Sparkles size={16}/>} Ask RJ AI</button><button type="button" onClick={startVoice} className={`flex items-center justify-center gap-2 rounded-lg py-2 text-sm font-semibold ${voiceActive ? "bg-rose-600" : "bg-emerald-600"}`}><Mic size={16}/>{voiceActive ? "Stop listening" : "Speak command"}</button></div>
    </form>
    <div className={`mt-3 rounded-md p-3 text-xs ${voiceActive ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-100" : "border border-slate-700 bg-slate-950 text-slate-400"}`}><b>{voiceActive ? "● VOICE LISTENING IS ON" : "○ VOICE LISTENING IS OFF"}</b><br/>{voiceActive ? "Say a song command naturally. Example: Play Kesariya Arijit Singh." : "Click Speak command to turn on continuous voice listening."}{voiceActive && lastHeard ? <><br/>Heard: “{lastHeard}”</> : null}<label className="mt-2 flex items-center gap-2 text-slate-300">Recognition language<select value={voiceLanguage} disabled={voiceActive} onChange={event => setVoiceLanguage(event.target.value)} className="rounded bg-slate-900 px-2 py-1 text-xs"><option value="hi-IN">Hindi + Hinglish</option><option value="en-IN">English + song titles</option></select></label></div>
    <p className="muted mt-2 text-xs">Song requests typed in the RJ box open YouTube automatically after a short pause. Common command typos such as “paly” are accepted.</p>
    <div className="mt-3 grid grid-cols-3 gap-2"><button onClick={() => void call("/ai/playlist", { prompt, mood: "upbeat", duration_minutes: 60 })} className="rounded-md bg-slate-800 p-2 text-xs">Generate playlist</button><button onClick={() => void call("/ai/script", { prompt })} className="rounded-md bg-slate-800 p-2 text-xs">Generate script</button><button onClick={() => void call("/ai/news", { prompt, metadata: { headlines: [] } })} className="rounded-md bg-slate-800 p-2 text-xs">Hourly news</button></div>
    <form onSubmit={findMusic} className="mt-4 flex gap-2"><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search songs online: Arijit Singh" className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 p-2 text-sm"/><button className="rounded-md bg-slate-800 px-3"><Search size={16}/></button></form>
    {results.length > 0 && <div className="mt-3 max-h-44 space-y-1 overflow-auto">{results.map(item => <div key={item.id} className="rounded-md bg-slate-950 p-2 text-xs"><b>{item.title}</b> <span className="muted">— {item.artist}</span><br/><span className="muted">Online catalogue result: add a licensed/local copy to your Library to play it.</span></div>)}</div>}
    <div className="mt-4 flex gap-2"><Volume2 size={16} className="mt-1 text-violet-300"/><p className="rounded-lg bg-slate-950/70 p-3 text-sm leading-6 text-slate-300">{response}</p></div>
    {status && <p className="muted mt-2 text-xs">{status.pending_approvals} proposal(s) awaiting RJ approval</p>}
  </section>;
}
