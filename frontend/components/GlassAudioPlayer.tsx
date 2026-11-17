"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  MoreVertical,
  Pause,
  Play,
  Repeat,
  RotateCcw,
} from "lucide-react";

type Song = {
  id: number;
  title: string;
  artist: string;
  duration_seconds: number;
  file_path: string;
};

type Props = {
  audioRef: React.RefObject<HTMLAudioElement | null>;
  audioUrl: string | null;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onEnded: () => void;
  currentSong?: Song | null;
  className?: string;
};

function formatTime(seconds: number): string {
  if (isNaN(seconds) || seconds <= 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export default function GlassAudioPlayer({
  audioRef,
  audioUrl,
  isPlaying,
  onTogglePlay,
  onEnded,
  currentSong,
  className = "",
}: Props) {
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(currentSong?.duration_seconds || 0);
  const [isSeeking, setIsSeeking] = useState<boolean>(false);
  const isDraggingRef = useRef<boolean>(false);
  const [showMenu, setShowMenu] = useState<boolean>(false);
  const [playbackRate, setPlaybackRate] = useState<number>(1);
  const [isLooping, setIsLooping] = useState<boolean>(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const progressContainerRef = useRef<HTMLDivElement>(null);

  // High-framerate fluid progress tracker during active playback (~30-60fps)
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !isPlaying) return;

    let animId: number;
    let lastStamp = 0;

    const renderTick = (timestamp: number) => {
      if (timestamp - lastStamp >= 30) {
        if (!isDraggingRef.current && audio && !audio.paused && !audio.ended) {
          setCurrentTime(audio.currentTime);
        }
        lastStamp = timestamp;
      }
      animId = requestAnimationFrame(renderTick);
    };

    animId = requestAnimationFrame(renderTick);
    return () => cancelAnimationFrame(animId);
  }, [isPlaying, audioRef]);

  // Synchronize native audio events
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handleTimeUpdate = () => {
      if (!isDraggingRef.current && !isPlaying) {
        setCurrentTime(audio.currentTime);
      }
    };

    const handleLoadedMetadata = () => {
      if (audio.duration && !isNaN(audio.duration) && isFinite(audio.duration)) {
        setDuration(audio.duration);
      } else if (currentSong?.duration_seconds) {
        setDuration(currentSong.duration_seconds);
      }
    };

    const handleEndedInternal = () => {
      if (isLooping) {
        audio.currentTime = 0;
        void audio.play();
      } else {
        onEnded();
      }
    };

    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("loadedmetadata", handleLoadedMetadata);
    audio.addEventListener("ended", handleEndedInternal);

    return () => {
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
      audio.removeEventListener("ended", handleEndedInternal);
    };
  }, [audioRef, isPlaying, isLooping, onEnded, currentSong]);

  // Update duration if song changes
  useEffect(() => {
    if (currentSong?.duration_seconds) {
      setDuration(currentSong.duration_seconds);
    }
    setCurrentTime(0);
  }, [currentSong?.id, currentSong?.duration_seconds]);

  // Close menu on click outside
  useEffect(() => {
    const handleClickOutside = (e: globalThis.MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showMenu]);

  // Helper to calculate exact time from pointer coordinate
  const calcTimeFromPointer = (clientX: number): number => {
    if (!progressContainerRef.current) return 0;
    const rect = progressContainerRef.current.getBoundingClientRect();
    if (rect.width <= 0) return 0;
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const targetDuration = duration > 0 ? duration : (currentSong?.duration_seconds || 180);
    return ratio * targetDuration;
  };

  // Immediate 0-latency pointer event handlers for smooth scrubbing
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    isDraggingRef.current = true;
    setIsSeeking(true);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {}

    const newTime = calcTimeFromPointer(e.clientX);
    setCurrentTime(newTime);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();
    const newTime = calcTimeFromPointer(e.clientX);
    setCurrentTime(newTime);
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {}
    const finalTime = calcTimeFromPointer(e.clientX);
    setCurrentTime(finalTime);
    if (audioRef.current) {
      audioRef.current.currentTime = finalTime;
    }
    // Briefly hold seek lock so audio decoder catches up without jitter
    setTimeout(() => {
      isDraggingRef.current = false;
      setIsSeeking(false);
    }, 60);
  };

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {}
    isDraggingRef.current = false;
    setIsSeeking(false);
  };

  const handleRateChange = (rate: number) => {
    setPlaybackRate(rate);
    if (audioRef.current) {
      audioRef.current.playbackRate = rate;
    }
    setShowMenu(false);
  };

  const toggleLoop = () => {
    setIsLooping((prev) => !prev);
    setShowMenu(false);
  };

  const restartSong = () => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      setCurrentTime(0);
      void audioRef.current.play();
    }
    setShowMenu(false);
  };

  const progressPercent = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;

  return (
    <div
      className={`relative w-full rounded-full transition-all ${className}`}
      style={{
        background:
          "linear-gradient(145deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.02) 45%, rgba(16, 20, 30, 0.22) 100%), rgba(16, 20, 30, 0.30)",
        backdropFilter: "blur(20px) saturate(200%)",
        WebkitBackdropFilter: "blur(20px) saturate(200%)",
        border: "1px solid rgba(255, 255, 255, 0.18)",
        boxShadow:
          "inset 0 1.5px 1px 0 rgba(255, 255, 255, 0.32), inset 0 -1px 1px 0 rgba(0, 0, 0, 0.22), 0 16px 36px -8px rgba(0, 0, 0, 0.55)",
      }}
    >
      {/* Hidden native audio element for decoding, streaming, and hardware audio pipeline */}
      {audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          className="sr-only"
          preload="auto"
        />
      )}

      {/* Glass Player Capsule Controls */}
      <div className="flex h-12 w-full items-center gap-3 px-3.5 sm:px-4">
        {/* Play / Pause Toggle Button with Liquid Spring Physics */}
        <button
          type="button"
          onClick={onTogglePlay}
          className="liquid-shimmer grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white text-slate-950 shadow-md shadow-white/30 transition-transform duration-250 ease-[cubic-bezier(0.34,1.56,0.64,1)] hover:scale-110 hover:shadow-[0_0_16px_rgba(0,206,200,0.45)] active:scale-90 cursor-pointer"
          title={isPlaying ? "Pause audio" : "Play audio"}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" className="ml-0.5" />}
        </button>

        {/* Time display: 1:34 / 3:26 */}
        <div className="shrink-0 font-mono text-[11px] sm:text-xs font-semibold text-slate-200 tracking-tight select-none">
          <span>{formatTime(currentTime)}</span>
          <span className="mx-1 text-slate-500">/</span>
          <span className="text-slate-400">{formatTime(duration)}</span>
        </div>

        {/* Interactive Scrubbing Timeline Track with Fluid Pointer Drag */}
        <div
          ref={progressContainerRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          className={`group/track relative flex-1 h-8 flex items-center select-none touch-none ${
            isSeeking ? "cursor-grabbing" : "cursor-pointer"
          }`}
          title="Drag or click to seek position"
        >
          {/* Glass Rail Background */}
          <div
            className={`relative w-full rounded-full bg-white/15 overflow-hidden transition-[height] duration-150 ${
              isSeeking ? "h-2" : "h-1.5 group-hover/track:h-2"
            }`}
          >
            {/* Filled Caribbean Turquoise Progress Line (Liquid wave animation during active playback) */}
            <div
              className={`h-full rounded-full ${isPlaying ? "liquid-scrubber-progress" : ""}`}
              style={{
                width: `${progressPercent}%`,
                background: isPlaying
                  ? undefined
                  : "linear-gradient(90deg, #00CEC8 0%, #00CEC8 100%)",
                boxShadow: "0 0 12px rgba(0, 206, 200, 0.55)",
              }}
            />
          </div>

          {/* Glowing Scrubber Thumb Knob */}
          <div
            className={`absolute h-3.5 w-3.5 -translate-x-1/2 rounded-full bg-white shadow-[0_0_12px_#00CEC8] pointer-events-none transition-transform duration-75 ${
              isSeeking
                ? "opacity-100 scale-125 shadow-[0_0_16px_#00CEC8]"
                : "opacity-0 group-hover/track:opacity-100 group-hover/track:scale-110"
            }`}
            style={{
              left: `${progressPercent}%`,
            }}
          />
        </div>

        {/* Options 3-Dots Menu */}
        <div ref={menuRef} className="relative shrink-0">
          <button
            type="button"
            onClick={() => setShowMenu((prev) => !prev)}
            className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:text-white transition-all duration-200 hover:bg-white/10 active:scale-90 active:rotate-90 cursor-pointer"
            title="Audio options"
            aria-label="Audio options"
          >
            <MoreVertical size={16} />
          </button>

          {/* Liquid Frosted Glass Options Popover (Faithful to Sample Images & Video) */}
          {showMenu && (
            <div
              className="absolute right-0 bottom-full mb-2.5 z-50 w-48 rounded-[26px] p-2 space-y-1.5 liquid-dropdown-menu text-xs"
            >
              <button
                type="button"
                onClick={restartSong}
                className="liquid-dropdown-item flex w-full items-center gap-2.5 rounded-full px-3.5 py-2 text-left text-slate-200 hover:text-white hover:liquid-glass-pill-hover cursor-pointer"
                style={{ animationDelay: "0ms" }}
              >
                <RotateCcw size={14} className="text-white" />
                <span>Restart song</span>
              </button>

              <button
                type="button"
                onClick={toggleLoop}
                className={`liquid-dropdown-item flex w-full items-center justify-between rounded-full px-3.5 py-2 text-left cursor-pointer ${
                  isLooping
                    ? "liquid-glass-pill-active"
                    : "text-slate-200 hover:text-white hover:liquid-glass-pill-hover"
                }`}
                style={{ animationDelay: "28ms" }}
              >
                <div className="flex items-center gap-2">
                  <Repeat size={14} className={isLooping ? "text-white" : "text-slate-400"} />
                  <span>Loop track</span>
                </div>
                {isLooping && <Check size={13} className="text-white" />}
              </button>

              <div className="my-1 border-t border-white/14" />

              <div className="px-3.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Playback Speed
              </div>

              {[0.75, 1, 1.25, 1.5].map((rate, idx) => (
                <button
                  key={rate}
                  type="button"
                  onClick={() => handleRateChange(rate)}
                  className={`liquid-dropdown-item flex w-full items-center justify-between rounded-full px-3.5 py-1.5 text-left cursor-pointer ${
                    playbackRate === rate
                      ? "liquid-glass-pill-active font-bold"
                      : "text-slate-300 hover:text-white hover:liquid-glass-pill-hover"
                  }`}
                  style={{ animationDelay: `${(idx + 2) * 28}ms` }}
                >
                  <span>{rate === 1 ? "Normal (1x)" : `${rate}x`}</span>
                  {playbackRate === rate && <Check size={12} className="text-white" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
