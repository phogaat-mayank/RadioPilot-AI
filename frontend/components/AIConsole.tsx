"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  Bot,
  Check,
  Copy,
  LoaderCircle,
  Mic,
  Radio,
  Search,
  Send,
  Sparkles,
  Trash2,
  User,
  Volume2,
  VolumeX,
  Waves,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type Props = { token: string };

type ChatMessage = {
  id: string | number;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  model?: string;
};

type AIStatus = {
  mode: string;
  autopilot_enabled: boolean;
  pending_approvals: number;
};

type Discovery = {
  id: string;
  title: string;
  artist: string;
  duration_seconds: number;
  release_date: string | null;
};

type OnAirNews = {
  schedule_id: number;
  broadcast_at: string;
  duration_seconds: number;
  bullets: string[];
};

type SpeechWindow = Window & {
  SpeechRecognition?: new () => SpeechRecognition;
  webkitSpeechRecognition?: new () => SpeechRecognition;
};

type SpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  abort: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal?: boolean }> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};

export default function AIConsole({ token }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "initial",
      role: "assistant",
      content:
        "**Hello! I am NOVA**, your live FM Radio Jockey co-host and universal AI assistant! 🎙️✨\n\nI speak in clear **English** and **Simple Hindi (सरल और आसान हिंदी)**. You can ask me anything—radio show links, scripts, music playlists, science, coding, or any general question. How can I help you today?",
      created_at: new Date().toISOString(),
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState("");
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | number | null>(null);
  const [speakingId, setSpeakingId] = useState<string | number | null>(null);

  // Web Music Discovery
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Discovery[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Voice Studio
  const [voiceActive, setVoiceActive] = useState(false);
  const [novaVoiceStatus, setNovaVoiceStatus] = useState("NOVA voice ready (English / Hindi)");
  const [lastHeard, setLastHeard] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const voiceActiveRef = useRef(false);
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCommandRef = useRef<{ text: string; at: number }>({ text: "", at: 0 });
  const heardBulletinsRef = useRef(new Set<string>());
  const pendingBulletinsRef = useRef(new Set<string>());

  // Load and cache browser voices reliably
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

    const updateVoices = () => {
      const vList = window.speechSynthesis.getVoices();
      if (vList && vList.length > 0) {
        setVoices(vList);
      }
    };

    updateVoices();
    window.speechSynthesis.onvoiceschanged = updateVoices;

    return () => {
      if ("speechSynthesis" in window) {
        window.speechSynthesis.onvoiceschanged = null;
      }
    };
  }, []);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTo({
        top: chatContainerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, loading]);

  // Load chat history from backend
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch(`${API}/ai/chat/history?session_id=dashboard`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data: ChatMessage[] = await res.json();
          if (data && data.length > 0) {
            setMessages(data);
          }
        }
      } catch {
        // Non-blocking
      }
    };
    void fetchHistory();
  }, [token]);

  /**
   * Cleans and phonetically normalizes text for natural human-like speech.
   * - Expands acronyms (RJ -> R J, FM -> F M, AI -> A I) so they aren't spelled out weirdly.
   * - Strips all markdown markup (*, _, #, ~, `, >, |) so symbols aren't read.
   * - Strips stage directions ([Music in], (laughs)) and list markers (1., 2., •).
   * - Cleans hyphens and slashes so words are spoken smoothly.
   */
  const cleanForSpeech = (raw: string): string => {
    let text = raw;

    // Remove code blocks and inline code
    text = text.replace(/```[\s\S]*?```/g, " ");
    text = text.replace(/`([^`]+)`/g, "$1");

    // Remove stage directions, bracketed cues, parentheses notes: e.g. [Music In], (laughs), [0:30]
    text = text.replace(/\[[^\]]*\]/g, " ");
    text = text.replace(/\([^\)]*\)/g, " ");

    // Strip speaker headers and section markers
    text = text.replace(/^\s*(?:Host|RJ|Presenter|Announcer|RJ AI|RJ NOVA|NOVA|RJ Riya|Riya|User|Assistant|Note|Tip)\s*:\s*/gim, " ");
    text = text.replace(/^\s*(?:OPEN|LINK|AUDIENCE HOOK|OUTRO|INTRO|DELIVERY|CUE|SUMMARY|HEADLINES?)\s*:\s*/gim, " ");

    // Remove URLs and markdown links
    text = text.replace(/https?:\/\/\S+/gi, " ");
    text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

    // Remove emojis
    text = text.replace(
      /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F900}-\u{1F9FF}\u{1FA70}-\u{1FAFF}]/gu,
      " "
    );

    // Phonetic expansions for acronyms and special symbols so they are pronounced naturally
    text = text.replace(/\bRadioPilot AI\b/gi, "Radio Pilot A I");
    text = text.replace(/\bRadioPilot\b/gi, "Radio Pilot");
    text = text.replace(/\bRJ\b/g, "R J");
    text = text.replace(/\bFM\b/g, "F M");
    text = text.replace(/\bAI\b/g, "A I");
    text = text.replace(/\bBPM\b/g, "B P M");
    text = text.replace(/\bBGM\b/g, "B G M");
    text = text.replace(/\bAM\b/g, "A M");
    text = text.replace(/\bPM\b/g, "P M");
    text = text.replace(/\bvs\.?\b/gi, "versus");
    text = text.replace(/\be\.g\.?,?\b/gi, "for example");
    text = text.replace(/\bi\.e\.?,?\b/gi, "that is");
    text = text.replace(/\bapprox\.?\b/gi, "approximately");
    text = text.replace(/&/g, " and ");
    text = text.replace(/%/g, " percent ");
    text = text.replace(/\+/g, " plus ");
    text = text.replace(/\//g, " or ");

    // Replace hyphens between words with a space so engine does not say "hyphen"
    text = text.replace(/(\w)-(\w)/g, "$1 $2");

    // Strip markdown formatting symbols (*, _, #, ~, >, |, =, ^, @, $, \, {, }, <, >)
    text = text.replace(/[\*\_#\~>\|=\^@\$\\\{\}<>]/g, " ");

    // Strip list item markers (bullets, numbered lists like 1., 2.)
    text = text.replace(/^\s*[\d•\-*]\.?\s+/gm, " ");

    // Clean up punctuation repetitions and double quotes
    text = text.replace(/[""''`]/g, " ");
    text = text.replace(/([.!?]){2,}/g, "$1");
    text = text.replace(/\s+/g, " ");

    return text.trim();
  };

  /**
   * Strictly filters OUT all male voices.
   */
  const isMaleVoice = (voiceName: string): boolean => {
    const maleBlacklist = [
      "male", "man", "boy", "david", "mark", "george", "ravi", "hemant", "guy", "stefan",
      "pablo", "paul", "james", "richard", "clark", "steve", "michael", "daniel", "alok",
      "madhav", "prabhat", "anil", "ajay", "tarun", "deepak", "kunal", "rahul", "amit", "suresh"
    ];
    const lower = voiceName.toLowerCase();
    return maleBlacklist.some((kw) => lower.includes(kw));
  };

  /**
   * Find the single best high-end female voice matching the text script type:
   * - If Devanagari text (हिंदी): Use Hindi female voice (Microsoft Swara, Heera, Google हिन्दी)
   * - If Latin text (English): Use Indian English female voice (Microsoft Neerja, Priya, Google Indian English)
   */
  const getFemaleNovaVoice = (isDevanagari: boolean): SpeechSynthesisVoice | null => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
    const currentVoices = voices.length ? voices : window.speechSynthesis.getVoices();
    if (!currentVoices || currentVoices.length === 0) return null;

    // Filter out ANY male voice
    const femaleOnlyVoices = currentVoices.filter((v) => !isMaleVoice(v.name));

    if (isDevanagari) {
      // 1. Devanagari Hindi Text -> Prioritize Hindi (hi-IN) female voices
      const hindiPriorityNames = ["swara", "heera", "google हिन्दी", "kalpana", "ananya"];
      const hindiNamed = femaleOnlyVoices.find((v) => {
        const name = v.name.toLowerCase();
        const lang = v.lang.toLowerCase();
        return (lang.startsWith("hi") || name.includes("hindi")) && hindiPriorityNames.some((kw) => name.includes(kw));
      });
      if (hindiNamed) return hindiNamed;

      const anyHindiFemale = femaleOnlyVoices.find(
        (v) => v.lang.toLowerCase().startsWith("hi") || v.name.toLowerCase().includes("hindi")
      );
      if (anyHindiFemale) return anyHindiFemale;
    } else {
      // 2. English Text -> Prioritize Indian English (en-IN) female voices
      const indianEnglishNames = [
        "neerja", "priya", "google english (india)", "google india", "india english", "en-in", "en_in"
      ];
      const indianEnglishNamed = femaleOnlyVoices.find((v) => {
        const name = v.name.toLowerCase();
        const lang = v.lang.toLowerCase();
        const isEnIn = lang === "en-in" || lang === "en_in" || lang.includes("in");
        return (isEnIn || indianEnglishNames.some((kw) => name.includes(kw))) && !v.lang.toLowerCase().startsWith("hi");
      });
      if (indianEnglishNamed) return indianEnglishNamed;

      // Any en-IN voice in female list
      const anyEnIn = femaleOnlyVoices.find(
        (v) => (v.lang.toLowerCase() === "en-in" || v.lang.toLowerCase() === "en_in") && !v.lang.toLowerCase().startsWith("hi")
      );
      if (anyEnIn) return anyEnIn;
    }

    // 3. High quality natural global female voices (Aria, Jenny, Zira, Google English, Samantha)
    const naturalFemaleNames = ["aria", "jenny", "zira", "samantha", "victoria", "karen", "siri", "moira"];
    const naturalFemale = femaleOnlyVoices.find((v) => {
      const name = v.name.toLowerCase();
      return (
        naturalFemaleNames.some((kw) => name.includes(kw)) ||
        name.includes("female") ||
        (name.includes("google") && !name.includes("male"))
      );
    });
    if (naturalFemale) return naturalFemale;

    // 4. Any non-male fallback
    if (femaleOnlyVoices.length > 0) return femaleOnlyVoices[0];

    return null;
  };

  const stopSpeaking = () => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setSpeakingId(null);
    setNovaVoiceStatus("NOVA voice ready");
  };

  /**
   * Speaks the message in an authentic Indian female voice with natural cadence.
   * Triggered ONLY when the user clicks the "Listen Voice" button.
   */
  const speak = (
    id: string | number,
    rawMessage: string,
    onStart?: () => void,
    onFailure?: () => void
  ) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setNovaVoiceStatus("Speech synthesis not supported in this browser");
      onFailure?.();
      return;
    }

    const spokenText = cleanForSpeech(rawMessage);
    if (!spokenText) return;

    window.speechSynthesis.cancel();

    // Check if text is predominantly Devanagari Hindi or English
    const devanagariMatches = spokenText.match(/[\u0900-\u097F]/g);
    const isDevanagari = (devanagariMatches ? devanagariMatches.length : 0) > 6;
    const selectedVoice = getFemaleNovaVoice(isDevanagari);

    const utterance = new SpeechSynthesisUtterance(spokenText);
    if (selectedVoice) {
      utterance.voice = selectedVoice;
      utterance.lang = selectedVoice.lang;
    } else {
      utterance.lang = isDevanagari ? "hi-IN" : "en-IN";
    }

    utterance.rate = 0.96; // Clear natural radio cadence
    utterance.pitch = 1.08; // Warm, natural feminine pitch
    utterance.volume = 1.0;

    utterance.onstart = () => {
      setSpeakingId(id);
      setNovaVoiceStatus("NOVA is speaking on air...");
      onStart?.();
    };
    utterance.onend = () => {
      setSpeakingId(null);
      setNovaVoiceStatus("NOVA voice ready (English / Hindi)");
    };
    utterance.onerror = () => {
      setSpeakingId(null);
      setNovaVoiceStatus("Voice playback failed");
      onFailure?.();
    };

    window.speechSynthesis.speak(utterance);
    window.speechSynthesis.resume();
  };

  const copyToClipboard = async (id: string | number, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // Fallback
    }
  };

  // Safe song playback detection
  const requestedSong = (text: string): string | null => {
    const spoken = text.trim();
    if (/^(what|why|how|who|where|when|can you|explain|tell me|is there|kya|kyun|kaise)\b/i.test(spoken)) {
      return null;
    }
    const match =
      spoken.match(/^(?:youtube\s+)?(?:please\s+)?(?:play|bajao|chalao)\s+(?:song\s+|gaana\s+)?(.+)/i) ||
      spoken.match(/^(.+?)\s+(?:chalao|bajao|baja do|chala do)$/i) ||
      spoken.match(/^(?:\u0915\u0943\u092a\u092f\u093e\s*)?(?:\u092f\u0942\u091f\u094d\u092f\u0942\u092c\s*(?:\u092a\u0930)?\s*)?(?:\u092a\u094d\u0932\u0947|\u091a\u0932\u093e\u0913|\u092c\u091c\u093e\u0913)\s*(?:\u0917\u093e\u0928\u093e\s*)?(.+)$/);

    const song = match?.[1]?.replace(/^(?:song|gaana|\u0917\u093e\u0928\u093e)\s+/i, "").trim();
    if (song && song.length >= 2 && !["music", "song", "gaana", "radio"].includes(song.toLowerCase())) {
      return song;
    }
    return null;
  };

  const openYouTube = async (song: string) => {
    try {
      const result = await fetch(`${API}/ai/youtube/play-url?q=${encodeURIComponent(song)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await result.json();
      if (!result.ok) throw new Error(data.detail ?? "YouTube search failed");
      window.open(data.url, "_blank");
    } catch {
      // Fallback
    }
  };

  // Send message to NOVA with full station control
  const sendMessage = async (promptToSend: string) => {
    const text = promptToSend.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt("");
    setLoading(true);

    try {
      const clientTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata";
      const result = await fetch(`${API}/ai/chat`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: text,
          session_id: "dashboard",
          mood: "balanced",
          duration_minutes: 60,
          metadata: {
            timezone: clientTz,
            timezone_offset_minutes: -new Date().getTimezoneOffset(),
            local_time: new Date().toISOString(),
          },
        }),
      });
      const data = await result.json();
      if (!result.ok) throw new Error(data.detail ?? "NOVA request failed");

      const replyContent = data.response ?? "No response received from NOVA.";
      const assistantMsg: ChatMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content: replyContent,
        created_at: new Date().toISOString(),
        model: data.agent,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      if (data.mode) setStatus(data);
      // Immediately refresh station state, current playing track, volume, and playlists
      window.dispatchEvent(new Event("station-refresh"));
    } catch (error) {
      const errMsg: ChatMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content: `⚠️ **Error:** ${error instanceof Error ? error.message : "Failed to get response from NOVA."}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleClearHistory = async () => {
    if (!confirm("Are you sure you want to clear this conversation history?")) return;
    try {
      await fetch(`${API}/ai/chat/history?session_id=dashboard`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      setMessages([
        {
          id: Date.now(),
          role: "assistant",
          content: "बातचीत का इतिहास साफ़ कर दिया गया है! NOVA आपके नए सवाल के लिए तैयार है! 🚀✨",
          created_at: new Date().toISOString(),
        },
      ]);
    } catch {
      // Ignore
    }
  };

  // Music search
  const findMusic = async (event: FormEvent) => {
    event.preventDefault();
    if (search.trim().length < 2) return;
    setSearchLoading(true);
    try {
      const result = await fetch(`${API}/ai/music/search?q=${encodeURIComponent(search)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await result.json();
      if (!result.ok) throw new Error(data.detail ?? "Search unavailable");
      setResults(data);
      if (Array.isArray(data) && data.length === 0) {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            role: "assistant",
            content: `🔍 **Music Search:** No results found for "${search}". Try searching with another song title or artist name.`,
            created_at: new Date().toISOString(),
          },
        ]);
      }
    } catch (error) {
      const errMsg: ChatMessage = {
        id: Date.now(),
        role: "assistant",
        content: `⚠️ **Music Search Error:** ${error instanceof Error ? error.message : "Failed to search online music."}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setSearchLoading(false);
    }
  };

  // Universal Voice Recognition (Listens to English and Hindi)
  const stopVoice = () => {
    voiceActiveRef.current = false;
    if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setVoiceActive(false);
    setLastHeard("");
  };

  const startVoice = () => {
    const Speech = (window as SpeechWindow).SpeechRecognition || (window as SpeechWindow).webkitSpeechRecognition;
    if (!Speech) {
      alert("Voice speech recognition is supported in Google Chrome and Microsoft Edge.");
      return;
    }
    if (voiceActiveRef.current) {
      stopVoice();
      return;
    }
    const recognition = new Speech();
    recognitionRef.current = recognition;
    voiceActiveRef.current = true;
    setVoiceActive(true);
    recognition.lang = "hi-IN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 6;

    recognition.onresult = (event) => {
      const result = event.results[event.results.length - 1];
      const alternatives = Array.from(result)
        .map((item) => item.transcript.trim())
        .filter(Boolean);
      const transcript = alternatives[0];
      if (!transcript) return;

      setLastHeard(transcript);
      if (!result.isFinal) return;

      const now = Date.now();
      if (lastCommandRef.current.text === transcript.toLowerCase() && now - lastCommandRef.current.at < 2500) {
        return;
      }
      lastCommandRef.current = { text: transcript.toLowerCase(), at: now };
      void sendMessage(transcript);
    };

    recognition.onerror = () => {
      if (voiceActiveRef.current) {
        setNovaVoiceStatus("Microphone access unavailable. Please grant microphone permission.");
      }
    };

    recognition.onend = () => {
      if (!voiceActiveRef.current) return;
      restartTimerRef.current = setTimeout(() => {
        try {
          recognition.start();
        } catch {
          // Already restarting
        }
      }, 350);
    };

    try {
      recognition.start();
      setNovaVoiceStatus("Listening to you in English / Hindi...");
    } catch {
      voiceActiveRef.current = false;
      setVoiceActive(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage(inputPrompt);
    }
  };

  // Status and on-air news polling
  useEffect(() => {
    fetch(`${API}/ai/status`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then(setStatus)
      .catch(() => undefined);

    const checkScheduledNews = async () => {
      try {
        const result = await fetch(`${API}/ai/news/on-air`, { headers: { Authorization: `Bearer ${token}` } });
        if (!result.ok) return;
        const bulletin = (await result.json()) as OnAirNews | null;
        if (!bulletin || !bulletin.bullets.length) return;
        const bulletinKey = `${bulletin.schedule_id}-${bulletin.broadcast_at}`;
        if (heardBulletinsRef.current.has(bulletinKey) || pendingBulletinsRef.current.has(bulletinKey)) return;
        pendingBulletinsRef.current.add(bulletinKey);

        const announcement = `📢 **Hourly News Broadcast:**\n\n${bulletin.bullets.map((b) => `• ${b}`).join("\n")}`;
        const newsMsg: ChatMessage = {
          id: Date.now(),
          role: "assistant",
          content: announcement,
          created_at: new Date().toISOString(),
          model: "news-agent",
        };
        setMessages((prev) => [...prev, newsMsg]);
      } catch {
        // Best effort
      }
    };

    void checkScheduledNews();
    const scheduledNewsTimer = window.setInterval(() => void checkScheduledNews(), 8000);

    return () => {
      voiceActiveRef.current = false;
      if (restartTimerRef.current) clearTimeout(restartTimerRef.current);
      recognitionRef.current?.abort();
      window.clearInterval(scheduledNewsTimer);
    };
  }, [token]);

  // Markdown renderer component
  const renderFormattedContent = (content: string) => {
    const parts = content.split(/(```[\s\S]*?```)/g);
    return parts.map((part, index) => {
      if (part.startsWith("```") && part.endsWith("```")) {
        const firstLineBreak = part.indexOf("\n");
        const lang = firstLineBreak > 3 ? part.slice(3, firstLineBreak).trim() : "code";
        const codeText = firstLineBreak > 0 ? part.slice(firstLineBreak + 1, -3) : part.slice(3, -3);
        return (
          <div key={index} className="my-2 overflow-hidden rounded-lg border border-white/10 bg-slate-950/60 backdrop-blur-md">
            <div className="flex items-center justify-between border-b border-white/5 bg-white/5 px-3 py-1.5 text-xs text-slate-400">
              <span className="font-mono text-[#00CEC8]">{lang || "code"}</span>
              <button
                onClick={() => copyToClipboard(`code-${index}`, codeText)}
                className="flex items-center gap-1 text-slate-300 hover:text-white"
              >
                {copiedId === `code-${index}` ? <Check size={12} className="text-[#00CEC8]" /> : <Copy size={12} />}
                <span className="text-[10px]">{copiedId === `code-${index}` ? "Copied" : "Copy"}</span>
              </button>
            </div>
            <pre className="overflow-x-auto p-3 font-mono text-xs text-[#00CEC8]">{codeText}</pre>
          </div>
        );
      }

      const lines = part.split("\n");
      return (
        <div key={index} className="space-y-1.5">
          {lines.map((line, lIdx) => {
            if (!line.trim()) return <div key={lIdx} className="h-1" />;

            if (line.startsWith("### ")) {
              return (
                <h4 key={lIdx} className="mt-2 text-sm font-bold text-[#FF9C5F]">
                  {formatInline(line.slice(4))}
                </h4>
              );
            }
            if (line.startsWith("## ")) {
              return (
                <h3 key={lIdx} className="mt-3 text-base font-bold text-[#00CEC8]">
                  {formatInline(line.slice(3))}
                </h3>
              );
            }
            if (line.startsWith("# ")) {
              return (
                <h2 key={lIdx} className="mt-3 text-lg font-extrabold text-white">
                  {formatInline(line.slice(2))}
                </h2>
              );
            }

            if (line.match(/^[\*\-•]\s+/)) {
              return (
                <div key={lIdx} className="flex items-start gap-2 pl-1 text-slate-200">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#00CEC8]" />
                  <span className="flex-1">{formatInline(line.replace(/^[\*\-•]\s+/, ""))}</span>
                </div>
              );
            }

            const numMatch = line.match(/^(\d+)\.\s+(.*)/);
            if (numMatch) {
              return (
                <div key={lIdx} className="flex items-start gap-2 pl-1 text-slate-200">
                  <span className="shrink-0 font-bold text-[#00CEC8]">{numMatch[1]}.</span>
                  <span className="flex-1">{formatInline(numMatch[2])}</span>
                </div>
              );
            }

            if (line.startsWith("> ")) {
              return (
                <blockquote
                  key={lIdx}
                  className="my-1 border-l-2 border-[#00CEC8] bg-[#00CEC8]/10 py-1 pl-3 text-xs italic text-slate-300"
                >
                  {formatInline(line.slice(2))}
                </blockquote>
              );
            }

            return (
              <p key={lIdx} className="text-slate-200">
                {formatInline(line)}
              </p>
            );
          })}
        </div>
      );
    });
  };

  const formatInline = (text: string) => {
    const tokens = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);
    return tokens.map((token, idx) => {
      if (token.startsWith("`") && token.endsWith("`")) {
        return (
          <code key={idx} className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-xs text-[#FCEFC3]">
            {token.slice(1, -1)}
          </code>
        );
      }
      if (token.startsWith("**") && token.endsWith("**")) {
        return (
          <strong key={idx} className="font-semibold text-white">
            {token.slice(2, -2)}
          </strong>
        );
      }
      if (token.startsWith("*") && token.endsWith("*")) {
        return (
          <em key={idx} className="italic text-slate-300">
            {token.slice(1, -1)}
          </em>
        );
      }
      return token;
    });
  };

  return (
    <section className="panel panel-floating-delayed flex flex-col overflow-hidden">
      {/* Clean Studio Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-white/5 p-4 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="grid h-10 w-10 place-items-center rounded-2xl bg-[#00CEC8] text-[#032023] shadow-lg shadow-[#00CEC8]/25">
              <Sparkles size={20} />
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#EB4203] opacity-75"></span>
              <span className="relative inline-flex h-3 w-3 rounded-full bg-[#EB4203]"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white">NOVA · Live AI Studio</h2>
              <span className="badge-turquoise text-[10px] py-0.5 px-2">
                🎙️ Indian Female Voice
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Universal Co-host · English · सरल हिन्दी
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {speakingId && (
            <button
              onClick={stopSpeaking}
              className="flex items-center gap-1 rounded-lg bg-rose-500/20 px-2.5 py-1 text-xs font-semibold text-rose-300 border border-rose-500/30 hover:bg-rose-500/30 transition"
              title="Stop speaking"
            >
              <VolumeX size={14} className="animate-pulse" /> Stop Voice
            </button>
          )}

          <button
            onClick={handleClearHistory}
            className="glass-capsule flex items-center gap-1 px-3 py-1 text-xs text-slate-300 hover:text-white transition"
            title="Clear chat session"
          >
            <Trash2 size={13} /> Clear Chat
          </button>

          <span
            className={
              status?.autopilot_enabled
                ? "badge-turquoise text-xs"
                : "badge-coral text-xs"
            }
          >
            {status?.mode ?? "MANUAL"}
          </span>
        </div>
      </div>

      {/* Chat Messages Stream */}
      <div
        ref={chatContainerRef}
        className="flex-1 space-y-4 overflow-y-auto p-4 max-h-[500px] min-h-[360px] bg-slate-950/20"
      >
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          const isSpeaking = speakingId === msg.id;

          return (
            <div
              key={msg.id}
              className={`flex items-start gap-3 text-sm animate-in fade-in slide-in-from-bottom-1 duration-200 ${
                isUser ? "flex-row-reverse" : "flex-row"
              }`}
            >
              {/* Avatar */}
              <div
                className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl text-xs font-bold shadow-md ${
                  isUser
                    ? "bg-white text-slate-950"
                    : "bg-[#00CEC8] text-[#032023] shadow-[#00CEC8]/20"
                }`}
              >
                {isUser ? <User size={15} /> : <Bot size={15} />}
              </div>

              {/* Message Bubble */}
              <div
                className={`group relative max-w-[85%] rounded-2xl p-4 transition-all ${
                  isUser
                    ? "bg-white/[0.09] text-white rounded-tr-none border border-white/20 backdrop-blur-xl shadow-lg [box-shadow:inset_0_1px_1px_rgba(255,255,255,0.25)]"
                    : "glass-subcard text-slate-100 rounded-tl-none"
                }`}
              >
                {/* Header info */}
                <div className="mb-1.5 flex items-center justify-between gap-3 text-[11px] opacity-75">
                  <span className="font-semibold text-[#00CEC8]">{isUser ? "You" : "NOVA"}</span>
                  {msg.created_at && (
                    <span>
                      {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                </div>

                {/* Content */}
                <div className="leading-relaxed text-sm">
                  {isUser ? <p className="whitespace-pre-wrap">{msg.content}</p> : renderFormattedContent(msg.content)}
                </div>

                {/* Action Bar for AI replies */}
                {!isUser && (
                  <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-2 text-xs text-slate-400">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => copyToClipboard(msg.id, msg.content)}
                        className="flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-white/10 hover:text-slate-200 transition-colors"
                        title="Copy text"
                      >
                        {copiedId === msg.id ? (
                          <>
                            <Check size={12} className="text-[#00CEC8]" />
                            <span className="text-[10px] text-[#00CEC8]">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy size={12} />
                            <span className="text-[10px]">Copy</span>
                          </>
                        )}
                      </button>

                      <button
                        onClick={() => (isSpeaking ? stopSpeaking() : speak(msg.id, msg.content))}
                        className={`badge-coral text-[11px] px-2.5 py-1 ${
                          isSpeaking ? "animate-pulse" : ""
                        }`}
                        title={isSpeaking ? "Stop voice" : "Listen to NOVA in authentic female voice"}
                      >
                        {isSpeaking ? <VolumeX size={13} className="animate-pulse" /> : <Volume2 size={13} />}
                        <span>{isSpeaking ? "Speaking..." : "Listen Voice"}</span>
                      </button>
                    </div>

                    {msg.model && (
                      <span className="font-mono text-[10px] text-slate-500">
                        {msg.model.replace("groq/", "")}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Loading Bubble */}
        {loading && (
          <div className="flex items-start gap-3 animate-in fade-in duration-150">
            <div className="grid h-8 w-8 place-items-center rounded-xl bg-[#00CEC8] text-[#032023]">
              <Sparkles size={15} className="animate-spin" />
            </div>
            <div className="glass-subcard flex items-center gap-2 rounded-2xl rounded-tl-none p-4 text-xs text-slate-300">
              <LoaderCircle className="animate-spin text-[#00CEC8]" size={16} />
              <span className="font-medium">NOVA is thinking and preparing the broadcast answer...</span>
            </div>
          </div>
        )}
      </div>

      {/* Voice Status Listening Banner */}
      {voiceActive && (
        <div className="flex items-center justify-between border-t border-[#00CEC8]/30 bg-[#00CEC8]/10 backdrop-blur-md px-4 py-2.5 text-xs text-slate-200">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#EB4203] opacity-75"></span>
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#EB4203]"></span>
            </span>
            <span className="font-semibold text-white">NOVA is listening (English / Hindi):</span>
            <span className="italic text-[#00CEC8]">{lastHeard ? `“${lastHeard}”` : "Speak to NOVA in English or Hindi..."}</span>
          </div>
          <button
            onClick={stopVoice}
            className="rounded-lg bg-rose-500 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-rose-600 transition"
          >
            Turn Off Mic
          </button>
        </div>
      )}

      {/* Clean Modern Input Box */}
      <div className="border-t border-white/10 bg-white/5 backdrop-blur-md p-4 space-y-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void sendMessage(inputPrompt);
          }}
          className="relative flex items-end gap-2"
        >
          <div className="relative flex-1">
            <textarea
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Ask NOVA anything in English or Hindi (सरल हिंदी)..."
              className="glass-input w-full resize-none p-3 pr-10 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
              aria-label="Message NOVA"
            />
          </div>

          <div className="flex items-center gap-1.5 pb-1">
            <button
              type="button"
              onClick={startVoice}
              className={`grid h-10 w-10 place-items-center rounded-xl transition-all ${
                voiceActive
                  ? "bg-rose-600 text-white shadow-lg shadow-rose-600/30 animate-pulse"
                  : "glass-subcard text-slate-300 hover:text-[#00CEC8]"
              }`}
              title={voiceActive ? "Stop microphone" : "Speak to NOVA in English or Hindi"}
            >
              <Mic size={18} />
            </button>

            <button
              type="submit"
              disabled={loading || !inputPrompt.trim()}
              className="grid h-10 w-10 place-items-center rounded-xl bg-[#00CEC8] hover:bg-[#00b5af] text-[#032023] font-bold shadow-lg shadow-[#00CEC8]/25 transition-all hover:scale-105 disabled:opacity-50 disabled:hover:scale-100"
              title="Send message to NOVA (Enter)"
            >
              {loading ? <LoaderCircle size={18} className="animate-spin" /> : <Send size={18} />}
            </button>
          </div>
        </form>

        {/* Live Audio Engine Status & Online Music Finder */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-white/10">
          <div className="flex items-center gap-1.5 text-xs text-[#00CEC8] font-medium">
            <Waves size={13} className="text-[#00CEC8] animate-pulse" />
            <span>{novaVoiceStatus}</span>
          </div>

          <form onSubmit={findMusic} className="flex items-center gap-1.5">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search online music..."
              className="glass-input py-1 pl-2.5 pr-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none w-44 md:w-56"
            />
            <button
              type="submit"
              disabled={searchLoading}
              className="rounded-lg bg-[#00CEC8] hover:bg-[#00b5af] px-3 py-1 text-xs font-bold text-[#032023] transition"
            >
              {searchLoading ? <LoaderCircle size={12} className="animate-spin" /> : <Search size={12} />}
              <span>Find</span>
            </button>
          </form>
        </div>

        {/* Music Search Results Accordion */}
        {results.length > 0 && (
          <div className="max-h-36 space-y-1.5 overflow-y-auto rounded-xl border border-white/10 bg-slate-950/70 backdrop-blur-md p-2">
            <div className="flex items-center justify-between pb-1 text-[11px] font-semibold text-slate-400">
              <span>Music Results ({results.length})</span>
              <button onClick={() => setResults([])} className="text-slate-500 hover:text-slate-300">
                Close
              </button>
            </div>
            {results.map((item) => (
              <div
                key={item.id}
                className="glass-subcard flex items-center justify-between p-2 text-xs hover:border-[#00CEC8]/40 transition"
              >
                <div>
                  <b className="text-white">{item.title}</b> <span className="text-slate-400">— {item.artist}</span>
                </div>
                <button
                  onClick={() => void openYouTube(`${item.title} ${item.artist}`)}
                  className="badge-coral text-[11px] py-1 px-2.5 cursor-pointer"
                >
                  <Radio size={11} /> Play YouTube
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
