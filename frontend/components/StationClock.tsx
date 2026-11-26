"use client";

import { useEffect, useState } from "react";
import { Clock } from "lucide-react";

type Props = {
  className?: string;
};

/**
 * Live broadcast studio clock rendered inside a unified liquid glass capsule.
 * Delays dynamic time rendering until client mount to prevent SSR hydration mismatches
 * and lets operators click to toggle between 12-hour and 24-hour studio format.
 */
export default function StationClock({ className = "" }: Props) {
  const [now, setNow] = useState<Date | null>(null);
  const [use24Hour, setUse24Hour] = useState<boolean>(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("radiopilot_clock_24h");
      if (saved === "true") setUse24Hour(true);
    } catch {}

    setNow(new Date());

    // Align ticks closely to whole-second boundaries for smooth broadcast readouts
    let intervalId: number | undefined;
    const msUntilNextSecond = 1000 - new Date().getMilliseconds();
    const timeoutId = window.setTimeout(() => {
      setNow(new Date());
      intervalId = window.setInterval(() => {
        setNow(new Date());
      }, 1000);
    }, msUntilNextSecond);

    return () => {
      window.clearTimeout(timeoutId);
      if (intervalId !== undefined) window.clearInterval(intervalId);
    };
  }, []);

  const toggleFormat = () => {
    setUse24Hour((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("radiopilot_clock_24h", String(next));
      } catch {}
      return next;
    });
  };

  const formattedTime = now
    ? now
        .toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: !use24Hour,
        })
        .toUpperCase()
    : "--:--:--";

  const formattedDate = now
    ? now.toLocaleDateString([], {
        weekday: "short",
        day: "numeric",
        month: "short",
      })
    : "";

  const fullTitle = now
    ? `${now.toLocaleDateString([], {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      })} — Click to switch 12h / 24h`
    : "Station Clock";

  return (
    <button
      type="button"
      onClick={toggleFormat}
      title={fullTitle}
      aria-label={`Station clock: ${formattedTime}. Click to toggle 12-hour or 24-hour format`}
      className={`glass-capsule-bar liquid-shimmer flex items-center gap-2 px-3.5 py-1.5 text-xs transition hover:border-white/45 cursor-pointer select-none ${className}`}
    >
      <Clock size={14} className="text-[#00CEC8] shrink-0" />
      <span className="font-mono font-bold tracking-wide text-white tabular-nums">
        {formattedTime}
      </span>
      {formattedDate && (
        <>
          <span className="hidden sm:inline text-slate-500">·</span>
          <span className="hidden sm:inline text-[11px] font-medium text-slate-300">
            {formattedDate}
          </span>
        </>
      )}
    </button>
  );
}
