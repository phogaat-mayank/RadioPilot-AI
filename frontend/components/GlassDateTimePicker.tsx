"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { Calendar, ChevronDown, ChevronLeft, ChevronRight, Clock, X, Check } from "lucide-react";

type Props = {
  value: string; // ISO-like string e.g. "YYYY-MM-DDTHH:mm"
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
};

const pad = (n: number) => n.toString().padStart(2, "0");

const toValueString = (year: number, month: number, day: number, hours: number, minutes: number) =>
  `${year}-${pad(month + 1)}-${pad(day)}T${pad(hours)}:${pad(minutes)}`;

export default function GlassDateTimePicker({
  value,
  onChange,
  placeholder = "Choose date and time...",
  className = "",
  disabled = false,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Parse initial value or default to current date
  const parsedDate = useMemo(() => {
    if (!value) return null;
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }, [value]);

  const [currentViewDate, setCurrentViewDate] = useState<Date>(() => parsedDate ?? new Date());
  const [selectedDate, setSelectedDate] = useState<Date | null>(() => parsedDate);

  // Time state
  const initialHour24 = parsedDate ? parsedDate.getHours() : new Date().getHours();
  const initialMinutes = parsedDate ? parsedDate.getMinutes() : 0;

  const [hours12, setHours12] = useState<number>(() => {
    const h = initialHour24 % 12;
    return h === 0 ? 12 : h;
  });
  const [minutes, setMinutes] = useState<number>(() => initialMinutes);
  const [ampm, setAmpm] = useState<"AM" | "PM">(() => (initialHour24 >= 12 ? "PM" : "AM"));

  // Keep internal state in sync with external value
  useEffect(() => {
    if (value) {
      const d = new Date(value);
      if (!isNaN(d.getTime())) {
        setSelectedDate(d);
        setCurrentViewDate(d);
        const h24 = d.getHours();
        const h12 = h24 % 12;
        setHours12(h12 === 0 ? 12 : h12);
        setMinutes(d.getMinutes());
        setAmpm(h24 >= 12 ? "PM" : "AM");
      }
    } else {
      setSelectedDate(null);
    }
  }, [value]);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  const viewYear = currentViewDate.getFullYear();
  const viewMonth = currentViewDate.getMonth();

  const prevMonth = () => {
    setCurrentViewDate(new Date(viewYear, viewMonth - 1, 1));
  };

  const nextMonth = () => {
    setCurrentViewDate(new Date(viewYear, viewMonth + 1, 1));
  };

  // Build calendar matrix
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const firstDayWeekday = new Date(viewYear, viewMonth, 1).getDay(); // 0 is Sunday

  const commitDateTime = (newDate: Date | null, newH12 = hours12, newMin = minutes, newAmpm = ampm) => {
    if (!newDate) {
      onChange("");
      return;
    }
    let h24 = newH12 % 12;
    if (newAmpm === "PM") h24 += 12;

    const valStr = toValueString(newDate.getFullYear(), newDate.getMonth(), newDate.getDate(), h24, newMin);
    onChange(valStr);
  };

  const handleDayClick = (dayNum: number) => {
    const d = new Date(viewYear, viewMonth, dayNum);
    setSelectedDate(d);
    commitDateTime(d);
  };

  const handleSetNow = () => {
    const now = new Date();
    setSelectedDate(now);
    setCurrentViewDate(now);
    const h24 = now.getHours();
    const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
    const m = now.getMinutes();
    const period = h24 >= 12 ? "PM" : "AM";
    setHours12(h12);
    setMinutes(m);
    setAmpm(period);
    commitDateTime(now, h12, m, period);
  };

  const handleClear = () => {
    setSelectedDate(null);
    onChange("");
  };

  // Formatted display label for trigger
  const displayLabel = useMemo(() => {
    if (!selectedDate) return placeholder;
    return `${selectedDate.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    })}, ${pad(hours12)}:${pad(minutes)} ${ampm}`;
  }, [selectedDate, hours12, minutes, ampm, placeholder]);

  const isToday = (dayNum: number) => {
    const today = new Date();
    return (
      today.getFullYear() === viewYear &&
      today.getMonth() === viewMonth &&
      today.getDate() === dayNum
    );
  };

  const isDaySelected = (dayNum: number) => {
    if (!selectedDate) return false;
    return (
      selectedDate.getFullYear() === viewYear &&
      selectedDate.getMonth() === viewMonth &&
      selectedDate.getDate() === dayNum
    );
  };

  return (
    <div ref={containerRef} className={`relative w-full ${isOpen ? "z-50" : "z-10"} ${className}`}>
      {/* Liquid Frosted Glass Capsule Trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setIsOpen((prev) => !prev)}
        className={`group relative flex w-full items-center justify-between gap-2.5 rounded-full px-4 py-2.5 text-xs sm:text-sm font-medium transition-all duration-300 outline-none liquid-shimmer cursor-pointer ${
          isOpen
            ? "border-[1.5px] border-white/50 shadow-[0_0_0_1px_rgba(255,255,255,0.25),inset_0_2px_2.5px_rgba(255,255,255,0.75),0_14px_36px_-6px_rgba(0,0,0,0.75)] scale-[1.01]"
            : "border-[1.5px] border-white/22 hover:border-white/38 shadow-[inset_0_1.5px_2px_rgba(255,255,255,0.50),0_10px_24px_-4px_rgba(0,0,0,0.50)] hover:shadow-[inset_0_2px_2.5px_rgba(255,255,255,0.65),0_14px_30px_-4px_rgba(0,0,0,0.65)]"
        } ${disabled ? "opacity-50 cursor-not-allowed" : "hover:-translate-y-0.5 active:translate-y-0.5 active:scale-[0.97]"}`}
        style={{
          background:
            "linear-gradient(145deg, rgba(255, 255, 255, 0.18) 0%, rgba(255, 255, 255, 0.03) 45%, rgba(16, 20, 30, 0.24) 100%), rgba(16, 20, 30, 0.32)",
          backdropFilter: "blur(24px) saturate(210%)",
          WebkitBackdropFilter: "blur(24px) saturate(210%)",
        }}
      >
        <div className="flex min-w-0 items-center gap-2.5 truncate">
          <Calendar size={16} className="text-white shrink-0" />
          <span className={`truncate ${selectedDate ? "text-white font-semibold" : "text-slate-400"}`}>
            {displayLabel}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {selectedDate && !disabled && (
            <span
              onClick={(e) => {
                e.stopPropagation();
                handleClear();
              }}
              className="grid h-5 w-5 place-items-center rounded-full text-slate-400 hover:text-white hover:bg-white/15 transition cursor-pointer"
              title="Clear date"
            >
              <X size={12} />
            </span>
          )}
          <ChevronDown
            size={16}
            className={`transition-transform duration-350 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
              isOpen ? "rotate-180 text-white scale-110" : "text-slate-400 group-hover:text-slate-200"
            }`}
          />
        </div>
      </button>

      {/* Liquid Glass Calendar Popover (Faithful to Reference Sample Images & Video) */}
      {isOpen && (
        <div
          ref={menuRef}
          className="absolute left-0 right-0 z-[100] mt-2.5 w-full sm:w-[350px] rounded-[30px] p-4 space-y-3 liquid-dropdown-menu text-xs"
        >
          {/* Month & Year Header */}
          <div className="flex items-center justify-between pb-1 border-b border-white/10">
            <button
              type="button"
              onClick={prevMonth}
              className="grid h-8 w-8 place-items-center rounded-full text-slate-300 hover:text-white hover:bg-white/15 active:scale-90 transition cursor-pointer"
              title="Previous month"
            >
              <ChevronLeft size={16} />
            </button>

            <span className="font-bold text-sm tracking-wide text-white">
              {monthNames[viewMonth]} {viewYear}
            </span>

            <button
              type="button"
              onClick={nextMonth}
              className="grid h-8 w-8 place-items-center rounded-full text-slate-300 hover:text-white hover:bg-white/15 active:scale-90 transition cursor-pointer"
              title="Next month"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {/* Weekday Labels */}
          <div className="grid grid-cols-7 gap-1 text-center font-bold text-[10px] text-slate-400 uppercase tracking-wider">
            <span>Su</span>
            <span>Mo</span>
            <span>Tu</span>
            <span>We</span>
            <span>Th</span>
            <span>Fr</span>
            <span>Sa</span>
          </div>

          {/* Days Grid */}
          <div className="grid grid-cols-7 gap-1 text-center">
            {/* Blank offset tiles for first week */}
            {Array.from({ length: firstDayWeekday }).map((_, i) => (
              <div key={`empty-${i}`} className="h-8 w-8" />
            ))}

            {/* Days of month */}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const dayNum = i + 1;
              const selected = isDaySelected(dayNum);
              const today = isToday(dayNum);

              return (
                <button
                  key={`day-${dayNum}`}
                  type="button"
                  onClick={() => handleDayClick(dayNum)}
                  className={`grid h-8 w-8 place-items-center rounded-full text-xs font-semibold transition-all duration-150 cursor-pointer ${
                    selected
                      ? "liquid-glass-pill-active !text-white scale-105"
                      : "text-slate-200 hover:liquid-glass-pill-hover hover:text-white"
                  } ${today && !selected ? "ring-1 ring-white/40" : ""}`}
                >
                  {dayNum}
                </button>
              );
            })}
          </div>

          {/* Time Picker Section */}
          <div className="pt-2 border-t border-white/10 space-y-2">
            <div className="flex items-center justify-between text-slate-300 font-medium">
              <span className="flex items-center gap-1.5 text-[11px] text-slate-400">
                <Clock size={13} className="text-white" /> Airtime
              </span>

              {/* AM / PM Toggle Pills */}
              <div className="glass-capsule-bar flex items-center p-0.5 text-[11px]">
                <button
                  type="button"
                  onClick={() => {
                    setAmpm("AM");
                    commitDateTime(selectedDate ?? new Date(), hours12, minutes, "AM");
                  }}
                  className={`px-2.5 py-0.5 rounded-full font-bold transition cursor-pointer ${
                    ampm === "AM" ? "liquid-glass-pill-active text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  AM
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAmpm("PM");
                    commitDateTime(selectedDate ?? new Date(), hours12, minutes, "PM");
                  }}
                  className={`px-2.5 py-0.5 rounded-full font-bold transition cursor-pointer ${
                    ampm === "PM" ? "liquid-glass-pill-active text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  PM
                </button>
              </div>
            </div>

            {/* Hours and Minutes Capsule Controls */}
            <div className="grid grid-cols-2 gap-2">
              <div className="flex items-center gap-1 bg-white/10 rounded-2xl px-2.5 py-1.5 border border-white/15">
                <span className="text-[10px] text-slate-400 font-bold uppercase">Hour:</span>
                <select
                  value={hours12}
                  onChange={(e) => {
                    const h = Number(e.target.value);
                    setHours12(h);
                    commitDateTime(selectedDate ?? new Date(), h, minutes, ampm);
                  }}
                  className="bg-transparent text-white font-bold text-xs w-full focus:outline-none cursor-pointer"
                >
                  {Array.from({ length: 12 }).map((_, i) => (
                    <option key={`h-${i + 1}`} value={i + 1} className="bg-slate-900 text-white">
                      {i + 1}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-1 bg-white/10 rounded-2xl px-2.5 py-1.5 border border-white/15">
                <span className="text-[10px] text-slate-400 font-bold uppercase">Min:</span>
                <select
                  value={minutes}
                  onChange={(e) => {
                    const m = Number(e.target.value);
                    setMinutes(m);
                    commitDateTime(selectedDate ?? new Date(), hours12, m, ampm);
                  }}
                  className="bg-transparent text-white font-bold text-xs w-full focus:outline-none cursor-pointer"
                >
                  {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
                    <option key={`m-${m}`} value={m} className="bg-slate-900 text-white">
                      {pad(m)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Quick Action Buttons */}
          <div className="pt-2 border-t border-white/10 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleSetNow}
                className="rounded-full px-3 py-1 bg-white/10 hover:bg-white/20 border border-white/15 text-slate-200 hover:text-white text-[11px] font-semibold transition cursor-pointer"
              >
                Now
              </button>
              {selectedDate && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="rounded-full px-3 py-1 text-slate-400 hover:text-rose-300 text-[11px] transition cursor-pointer"
                >
                  Clear
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => {
                if (!selectedDate) {
                  const now = new Date();
                  setSelectedDate(now);
                  commitDateTime(now);
                }
                setIsOpen(false);
              }}
              className="liquid-glass-pill-active flex items-center gap-1.5 rounded-full px-4 py-1 text-xs text-white font-bold cursor-pointer"
            >
              <Check size={13} strokeWidth={2.8} /> Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
