"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  Globe,
  Info,
  Languages,
  Loader2,
  Mic,
  Play,
  Radio,
  Send,
  Sliders,
  Sparkles,
  Square,
  Volume1,
  Volume2,
  VolumeX,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type TTSVoice = {
  id: string;
  name: string;
  language: string;
  gender: string;
  description: string;
  sample_text: string;
  is_available: boolean;
};

export type AIDJSettings = {
  enabled: boolean;
  language: "en" | "hi";
  voice_id: string;
  frequency_songs: number;
  volume: number;
  intros_enabled: boolean;
  outros_enabled: boolean;
  time_greetings_enabled: boolean;
};

type Props = {
  token: string;
  onAnnouncementTriggered?: () => void;
};

function formatApiError(detail: unknown): string {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const msg = (item as { msg?: string }).msg || (item as { message?: string }).message;
          return msg ? String(msg) : JSON.stringify(item);
        }
        return String(item);
      })
      .join("; ");
  }
  return String(detail);
}

export default function AIDJVoiceSettings({ token, onAnnouncementTriggered }: Props) {
  const [settings, setSettings] = useState<AIDJSettings>({
    enabled: true,
    language: "en",
    voice_id: "en_US-lessac-medium",
    frequency_songs: 2,
    volume: 85,
    intros_enabled: true,
    outros_enabled: true,
    time_greetings_enabled: true,
  });

  const [voices, setVoices] = useState<TTSVoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; type: "success" | "error" | "info" } | null>(null);

  // Audition state
  const [auditioningVoiceId, setAuditioningVoiceId] = useState<string | null>(null);
  const [auditionLoading, setAuditionLoading] = useState(false);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);

  // Manual announcement state
  const [manualText, setManualText] = useState("");
  const [manualPlayImmediately, setManualPlayImmediately] = useState(true);
  const [broadcasting, setBroadcasting] = useState(false);

  // Load voices and settings from backend
  useEffect(() => {
    if (!token) return;
    let isCancelled = false;

    async function loadData() {
      setLoading(true);
      try {
        const [voicesRes, settingsRes] = await Promise.all([
          fetch(`${API}/tts/voices`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API}/tts/settings`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);

        if (!voicesRes.ok) throw new Error("Failed to load TTS voices catalog");
        if (!settingsRes.ok) throw new Error("Failed to load AI DJ settings");

        const voicesData = await voicesRes.json();
        const settingsData = await settingsRes.json();

        if (!isCancelled) {
          setVoices(voicesData);
          setSettings(settingsData);
        }
      } catch (err) {
        if (!isCancelled) {
          setNotice({
            text: err instanceof Error ? err.message : "Failed to load voice engine data",
            type: "error",
          });
        }
      } finally {
        if (!isCancelled) setLoading(false);
      }
    }

    void loadData();

    return () => {
      isCancelled = true;
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
      }
    };
  }, [token]);

  // Clean up preview audio on unmount
  useEffect(() => {
    return () => {
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
      }
    };
  }, []);

  // Save settings helper
  const saveSettings = async (updated: Partial<AIDJSettings>) => {
    const newSettings = { ...settings, ...updated };
    setSettings(newSettings);
    setSaving(true);
    setNotice(null);

    try {
      const res = await fetch(`${API}/tts/settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(updated),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(formatApiError(errJson?.detail || "Could not save AI DJ settings"));
      }

      const saved = await res.json();
      setSettings(saved);
      setNotice({ text: "AI DJ Voice settings updated", type: "success" });
      setTimeout(() => setNotice(null), 3000);
    } catch (err) {
      setNotice({
        text: err instanceof Error ? err.message : "Save failed",
        type: "error",
      });
    } finally {
      setSaving(false);
    }
  };

  // Switch language and pick first matching voice if current does not match
  const handleLanguageChange = (lang: "en" | "hi") => {
    const matchingVoices = voices.filter((v) => v.language === lang);
    const newVoiceId =
      matchingVoices.find((v) => v.id === settings.voice_id)?.id ||
      (matchingVoices.length > 0 ? matchingVoices[0].id : settings.voice_id);

    void saveSettings({
      language: lang,
      voice_id: newVoiceId,
    });
  };

  // Test / Audition Voice via /tts/preview
  const auditionVoice = async (voice: TTSVoice) => {
    // If already auditioning this voice, stop it
    if (auditioningVoiceId === voice.id) {
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
      }
      setAuditioningVoiceId(null);
      return;
    }

    // Stop any existing preview
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }

    setAuditionLoading(true);
    setAuditioningVoiceId(voice.id);
    setNotice(null);

    try {
      const res = await fetch(`${API}/tts/preview`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: voice.sample_text,
          voice_id: voice.id,
          language: voice.language,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(formatApiError(errJson?.detail || "Voice audition failed"));
      }

      const blob = await res.blob();
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      previewAudioRef.current = audio;
      audio.volume = Math.max(0, Math.min(1, settings.volume / 100));

      audio.onended = () => {
        setAuditioningVoiceId(null);
        URL.revokeObjectURL(audioUrl);
        previewAudioRef.current = null;
      };

      audio.onerror = () => {
        setAuditioningVoiceId(null);
        URL.revokeObjectURL(audioUrl);
        previewAudioRef.current = null;
        setNotice({ text: "Could not decode audio preview in browser", type: "error" });
      };

      await audio.play();
    } catch (err) {
      setAuditioningVoiceId(null);
      setNotice({
        text: err instanceof Error ? err.message : "Voice preview error",
        type: "error",
      });
    } finally {
      setAuditionLoading(false);
    }
  };

  // Broadcast manual announcement
  const handleBroadcastManual = async () => {
    if (!manualText.trim()) {
      setNotice({ text: "Please enter announcement text to broadcast", type: "error" });
      return;
    }

    setBroadcasting(true);
    setNotice(null);

    try {
      const res = await fetch(`${API}/tts/manual-announcement`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: manualText.trim(),
          voice_id: settings.voice_id,
          language: settings.language,
          play_immediately: manualPlayImmediately,
        }),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(formatApiError(errJson?.detail || "Failed to trigger broadcast announcement"));
      }

      const ann = await res.json();
      setManualText("");
      setNotice({
        text: manualPlayImmediately
          ? `🎙️ AI DJ announcement is now broadcasting live on air!`
          : `🎙️ AI DJ announcement queued for the next song transition!`,
        type: "success",
      });

      if (onAnnouncementTriggered) {
        onAnnouncementTriggered();
      }
      window.dispatchEvent(new CustomEvent("station-refresh"));
    } catch (err) {
      setNotice({
        text: err instanceof Error ? err.message : "Manual announcement failed",
        type: "error",
      });
    } finally {
      setBroadcasting(false);
    }
  };

  const filteredVoices = voices.filter((v) => v.language === settings.language);

  return (
    <section className="panel p-6 space-y-6">
      {/* Title & Master Enabled Switch */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#00CEC8] text-[#032023] font-bold shadow-lg shadow-[#00CEC8]/30">
            <Mic size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-extrabold text-white tracking-tight">AI DJ Voice Engine</h2>
              <span className="badge-turquoise text-[10px] py-0.5 px-2">Piper Neural TTS</span>
            </div>
            <p className="text-xs text-slate-400">
              100% Free • Self-Hosted Local Inference • Zero Cloud API Costs
            </p>
          </div>
        </div>

        {/* Master Toggle */}
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-slate-300">
            {settings.enabled ? "Voice Active" : "Voice Muted"}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={settings.enabled}
            onClick={() => void saveSettings({ enabled: !settings.enabled })}
            className={`relative inline-flex h-7 w-13 cursor-pointer rounded-full transition-colors duration-200 ease-in-out border border-white/15 ${
              settings.enabled ? "bg-[#00CEC8]" : "bg-white/10"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ease-in-out mt-0.5 ml-0.5 ${
                settings.enabled ? "translate-x-6 bg-[#032023]" : "translate-x-0 bg-slate-300"
              }`}
            />
          </button>
        </div>
      </div>

      {/* Notifications / Feedback */}
      {notice && (
        <div
          className={`flex items-center justify-between rounded-xl px-3.5 py-2.5 text-xs animate-in fade-in duration-200 border ${
            notice.type === "success"
              ? "border-[#00CEC8]/40 bg-[#00CEC8]/15 text-[#00CEC8]"
              : notice.type === "error"
              ? "border-rose-500/40 bg-rose-500/15 text-rose-300"
              : "border-sky-500/40 bg-sky-500/15 text-sky-200"
          }`}
        >
          <span>{notice.text}</span>
          <button
            onClick={() => setNotice(null)}
            className="ml-2 text-slate-400 hover:text-white"
            aria-label="Dismiss notice"
          >
            ×
          </button>
        </div>
      )}

      {/* Primary Configuration Grid */}
      <div className="grid gap-5 md:grid-cols-2">
        {/* Language Selection */}
        <div className="glass-subcard p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
              <Languages size={15} className="text-[#00CEC8]" />
              <span>Broadcast Language</span>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              {settings.language === "hi" ? "हिन्दी (Hindi)" : "English (US)"}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => handleLanguageChange("en")}
              className={`flex items-center justify-center gap-2 rounded-xl py-2.5 px-3 text-xs font-semibold transition border cursor-pointer ${
                settings.language === "en"
                  ? "bg-[#00CEC8] text-[#032023] font-bold border-transparent shadow-md shadow-[#00CEC8]/25"
                  : "bg-white/5 text-slate-300 hover:bg-white/10 border-white/10"
              }`}
            >
              <Globe size={14} />
              <span>English (US)</span>
            </button>
            <button
              type="button"
              onClick={() => handleLanguageChange("hi")}
              className={`flex items-center justify-center gap-2 rounded-xl py-2.5 px-3 text-xs font-semibold transition border cursor-pointer ${
                settings.language === "hi"
                  ? "bg-[#00CEC8] text-[#032023] font-bold border-transparent shadow-md shadow-[#00CEC8]/25"
                  : "bg-white/5 text-slate-300 hover:bg-white/10 border-white/10"
              }`}
            >
              <span>हिन्दी (Hindi)</span>
            </button>
          </div>
          <p className="text-[11px] text-slate-400">
            {settings.language === "hi"
              ? "प्राकृतिक भारतीय उच्चारण में उद्घोषणाएँ (Devanagari script support included)."
              : "Natural, expressive studio announcements for American and international English."}
          </p>
        </div>

        {/* Announcement Frequency */}
        <div className="glass-subcard p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
              <Sliders size={15} className="text-[#FF9C5F]" />
              <span>Announcement Frequency</span>
            </div>
            <span className="text-xs font-bold text-[#FF9C5F]">
              Every {settings.frequency_songs} {settings.frequency_songs === 1 ? "song" : "songs"}
            </span>
          </div>

          <div className="grid grid-cols-4 gap-1.5">
            {[1, 2, 3, 5].map((count) => (
              <button
                key={count}
                type="button"
                onClick={() => void saveSettings({ frequency_songs: count })}
                className={`rounded-xl py-2 text-xs font-semibold transition border cursor-pointer ${
                  settings.frequency_songs === count
                    ? "bg-[#FF9C5F] text-[#2b1102] font-bold border-transparent shadow-md shadow-[#FF9C5F]/25"
                    : "bg-white/5 text-slate-300 hover:bg-white/10 border-white/10"
                }`}
              >
                1 / {count} {count === 1 ? "track" : "tracks"}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-slate-400">
            AI DJ prepares and delivers an intro/outro between tracks at this cadence.
          </p>
        </div>
      </div>

      {/* Voice Selection Cards */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio size={16} className="text-[#00CEC8]" />
            <h3 className="text-sm font-bold text-white">
              Available RJ Voice Models ({filteredVoices.length})
            </h3>
          </div>
          <span className="text-[11px] text-slate-400">
            Click card to activate • Click Test Voice to audition
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {filteredVoices.map((voice) => {
            const isSelected = settings.voice_id === voice.id;
            const isAuditioning = auditioningVoiceId === voice.id;

            return (
              <div
                key={voice.id}
                onClick={() => void saveSettings({ voice_id: voice.id })}
                className={`glass-subcard relative p-4 transition-all cursor-pointer ${
                  isSelected
                    ? "border-[#00CEC8]/60 bg-gradient-to-br from-[#00CEC8]/15 via-white/5 to-transparent ring-1 ring-[#00CEC8]/50 shadow-lg shadow-[#00CEC8]/10"
                    : "hover:border-white/20"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`grid h-10 w-10 place-items-center rounded-xl font-bold shadow-md ${
                        isSelected
                          ? "bg-[#00CEC8] text-[#032023]"
                          : "bg-white/10 text-slate-300"
                      }`}
                    >
                      {voice.gender === "female" ? "♀" : "♂"}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-white">{voice.name}</h4>
                        <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded-md bg-white/10 text-slate-300">
                          {voice.gender}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">{voice.description}</p>
                    </div>
                  </div>

                  {isSelected && (
                    <div className="grid h-6 w-6 place-items-center rounded-full bg-[#00CEC8] text-[#032023] shadow-md shadow-[#00CEC8]/30">
                      <Check size={14} />
                    </div>
                  )}
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-3">
                  <span className="text-[10px] font-mono text-slate-500 truncate max-w-[180px]">
                    {voice.id}
                  </span>

                  {/* Test Voice Audition Button */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void auditionVoice(voice);
                    }}
                    disabled={auditionLoading && auditioningVoiceId === voice.id}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold transition cursor-pointer ${
                      isAuditioning
                        ? "bg-[#EB4203] text-white shadow-md shadow-[#EB4203]/30 animate-pulse"
                        : "bg-white/10 text-slate-200 hover:bg-[#00CEC8] hover:text-[#032023]"
                    }`}
                    title={isAuditioning ? "Stop audio preview" : `Test ${voice.name}'s voice`}
                  >
                    {isAuditioning ? (
                      <>
                        <Square size={12} fill="currentColor" />
                        <span>Stop Test</span>
                      </>
                    ) : (
                      <>
                        <Play size={12} fill="currentColor" />
                        <span>Test Voice</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Voice Volume & Automation Modules */}
      <div className="grid gap-5 md:grid-cols-2">
        {/* DJ Voice Volume */}
        <div className="glass-subcard p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300">
              <Volume2 size={15} className="text-[#00CEC8]" />
              <span>DJ Voice Broadcast Volume</span>
            </div>
            <span className="font-mono text-xs font-bold text-white">{settings.volume}%</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void saveSettings({ volume: settings.volume === 0 ? 85 : 0 })}
              className="text-slate-400 hover:text-white"
            >
              {settings.volume === 0 ? <VolumeX size={18} /> : <Volume1 size={18} />}
            </button>
            <input
              type="range"
              min="0"
              max="100"
              value={settings.volume}
              onChange={(e) => setSettings((prev) => ({ ...prev, volume: Number(e.target.value) }))}
              onMouseUp={(e) => void saveSettings({ volume: Number(e.currentTarget.value) })}
              onTouchEnd={(e) => void saveSettings({ volume: Number(e.currentTarget.value) })}
              className="w-full accent-[#00CEC8] cursor-pointer"
            />
          </div>
          <p className="text-[11px] text-slate-400">
            Relative speech output level mixed with music playback transitions.
          </p>
        </div>

        {/* Content Toggles */}
        <div className="glass-subcard p-4 space-y-2.5">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Speech Features
          </div>
          <div className="space-y-2">
            <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
              <span>Track Intros (Introduce upcoming song & artist)</span>
              <input
                type="checkbox"
                checked={settings.intros_enabled}
                onChange={(e) => void saveSettings({ intros_enabled: e.target.checked })}
                className="rounded accent-[#00CEC8] h-4 w-4 cursor-pointer"
              />
            </label>
            <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
              <span>Track Outros (Recap just finished song)</span>
              <input
                type="checkbox"
                checked={settings.outros_enabled}
                onChange={(e) => void saveSettings({ outros_enabled: e.target.checked })}
                className="rounded accent-[#00CEC8] h-4 w-4 cursor-pointer"
              />
            </label>
            <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer">
              <span>Time-based Greetings (Morning / Afternoon / Night station IDs)</span>
              <input
                type="checkbox"
                checked={settings.time_greetings_enabled}
                onChange={(e) => void saveSettings({ time_greetings_enabled: e.target.checked })}
                className="rounded accent-[#00CEC8] h-4 w-4 cursor-pointer"
              />
            </label>
          </div>
        </div>
      </div>

      {/* Manual Live Announcement Studio */}
      <div className="glass-subcard p-5 space-y-4 border-white/15">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[#FCEFC3]" />
            <h3 className="text-sm font-bold text-white">Manual Live Announcement Studio</h3>
          </div>
          <span className="badge-cream text-[10px] py-0.5 px-2">On-Demand DJ Speech</span>
        </div>

        <p className="text-xs text-slate-400">
          Type any custom announcement below. The neural voice engine will synthesize and broadcast it
          using the selected RJ ({filteredVoices.find((v) => v.id === settings.voice_id)?.name || "Default RJ"}).
        </p>

        {/* Quick Template Buttons */}
        <div className="flex flex-wrap gap-2 text-xs">
          <button
            type="button"
            onClick={() =>
              setManualText(
                settings.language === "hi"
                  ? "नमस्ते श्रोताओं! रेडियोपायलट एआई पर आपका स्वागत है। बेहतरीन संगीत का मज़ा लेते रहिए।"
                  : "Welcome to RadioPilot AI! Hope you are enjoying the smooth vibes and great tunes today."
              )
            }
            className="rounded-lg bg-white/5 border border-white/10 px-2.5 py-1 text-slate-300 hover:bg-white/10 transition"
          >
            + Welcome Listeners
          </button>
          <button
            type="button"
            onClick={() =>
              setManualText(
                settings.language === "hi"
                  ? "यह है रेडियोपायलट एआई। अगला शानदार गाना बस कुछ ही पलों में!"
                  : "You're locked in to RadioPilot AI. Another massive track is heading your way right now!"
              )
            }
            className="rounded-lg bg-white/5 border border-white/10 px-2.5 py-1 text-slate-300 hover:bg-white/10 transition"
          >
            + Next Song Tease
          </button>
          <button
            type="button"
            onClick={() =>
              setManualText(
                settings.language === "hi"
                  ? "समय हो चला है अगले म्यूज़िकल सेगमेंट का। रेडियोपायलट एआई के साथ बने रहिए!"
                  : "Thanks for hanging out with us on RadioPilot AI. Stay tuned for nonstop musical flow!"
              )
            }
            className="rounded-lg bg-white/5 border border-white/10 px-2.5 py-1 text-slate-300 hover:bg-white/10 transition"
          >
            + Station ID
          </button>
        </div>

        {/* Text Input */}
        <div className="relative">
          <textarea
            rows={3}
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            placeholder={
              settings.language === "hi"
                ? "यहाँ अपनी उद्घोषणा लिखें (जैसे: 'रेडियोपायलट एआई पर आपका स्वागत है...')..."
                : "Enter announcement text to broadcast on air (e.g., 'Welcome back to RadioPilot AI...')..."
            }
            className="glass-input w-full p-3 text-xs text-white placeholder-slate-500 focus:outline-none resize-none"
          />
          <div className="absolute right-2 bottom-2 text-[10px] text-slate-500">
            {manualText.length} chars
          </div>
        </div>

        {/* Broadcast Action Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={manualPlayImmediately}
              onChange={(e) => setManualPlayImmediately(e.target.checked)}
              className="rounded accent-[#00CEC8] h-4 w-4 cursor-pointer"
            />
            <span>Broadcast immediately (cue live on air now)</span>
          </label>

          <button
            type="button"
            disabled={broadcasting || !manualText.trim()}
            onClick={() => void handleBroadcastManual()}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#00CEC8] to-[#00b5af] hover:brightness-110 px-4 py-2.5 text-xs font-bold text-[#032023] shadow-lg shadow-[#00CEC8]/30 transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {broadcasting ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                <span>Synthesizing Voice...</span>
              </>
            ) : (
              <>
                <Send size={14} />
                <span>Broadcast Announcement Now</span>
              </>
            )}
          </button>
        </div>
      </div>
    </section>
  );
}
