"use client";

import { useEffect, useRef, useState, useMemo, ReactNode, KeyboardEvent as ReactKeyboardEvent } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";

export type GlassSelectOption<T extends string | number> = {
  value: T;
  label: string;
  icon?: ReactNode;
};

type Props<T extends string | number> = {
  value: T;
  onChange: (value: T) => void;
  options: Array<GlassSelectOption<T>>;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
};

export default function GlassSelect<T extends string | number>({
  value,
  onChange,
  options,
  placeholder = "Select...",
  className = "",
  disabled = false,
}: Props<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Filter options if large list has active search query
  const filteredOptions = useMemo(() => {
    if (!searchQuery.trim()) return options;
    const q = searchQuery.toLowerCase().trim();
    return options.filter((opt) => opt.label.toLowerCase().includes(q));
  }, [options, searchQuery]);

  const selectedIndex = filteredOptions.findIndex((opt) => opt.value === value);
  const selectedOption = options.find((opt) => opt.value === value);

  // Reset or initialize state when opening / closing
  useEffect(() => {
    if (isOpen) {
      setHighlightedIndex(selectedIndex >= 0 ? selectedIndex : 0);
      setSearchQuery("");
      // Scroll to selected item inside the dropdown without moving the page window
      requestAnimationFrame(() => {
        if (scrollContainerRef.current && selectedIndex > 0) {
          const items = scrollContainerRef.current.querySelectorAll<HTMLElement>("[data-select-item]");
          const target = items[selectedIndex];
          if (target) {
            scrollContainerRef.current.scrollTop = Math.max(0, target.offsetTop - 40);
          }
        }
      });
    } else {
      setSearchQuery("");
    }
  }, [isOpen]);

  // Close when clicking outside
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

  const handleSelect = (val: T) => {
    onChange(val);
    setIsOpen(false);
  };

  // Scroll to keep highlighted item in view during KEYBOARD navigation ONLY
  const scrollToHighlighted = (index: number) => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const items = container.querySelectorAll<HTMLElement>("[data-select-item]");
    const target = items[index];
    if (!target) return;

    const itemTop = target.offsetTop;
    const itemBottom = itemTop + target.offsetHeight;
    const containerTop = container.scrollTop;
    const containerBottom = containerTop + container.clientHeight;

    if (itemTop < containerTop) {
      container.scrollTo({ top: Math.max(0, itemTop - 6), behavior: "smooth" });
    } else if (itemBottom > containerBottom) {
      container.scrollTo({ top: itemBottom - container.clientHeight + 6, behavior: "smooth" });
    }
  };

  const handleKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;

    if (!isOpen) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "Escape":
      case "Tab":
        e.preventDefault();
        setIsOpen(false);
        break;
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((prev) => {
          const next = prev + 1 < filteredOptions.length ? prev + 1 : 0;
          scrollToHighlighted(next);
          return next;
        });
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((prev) => {
          const next = prev - 1 >= 0 ? prev - 1 : filteredOptions.length - 1;
          scrollToHighlighted(next);
          return next;
        });
        break;
      case "Home":
        e.preventDefault();
        setHighlightedIndex(0);
        scrollToHighlighted(0);
        break;
      case "End":
        e.preventDefault();
        setHighlightedIndex(filteredOptions.length - 1);
        scrollToHighlighted(filteredOptions.length - 1);
        break;
      case "Enter":
      case " ":
        if (e.target === searchInputRef.current && e.key === " ") {
          // Allow space in search input
          return;
        }
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < filteredOptions.length) {
          handleSelect(filteredOptions[highlightedIndex].value);
        }
        break;
    }
  };

  return (
    <div
      ref={containerRef}
      onKeyDown={handleKeyDown}
      className={`relative w-full ${isOpen ? "z-50" : "z-10"} ${className}`}
    >
      {/* 3D Liquid Frosted Glass Capsule Trigger */}
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
        <div className="flex min-w-0 items-center gap-2 truncate">
          {selectedOption?.icon}
          <span className={`truncate ${selectedOption ? "text-white font-semibold" : "text-slate-400"}`}>
            {selectedOption ? selectedOption.label : placeholder}
          </span>
        </div>

        <ChevronDown
          size={16}
          className={`shrink-0 transition-transform duration-350 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            isOpen ? "rotate-180 text-white scale-110" : "text-slate-400 group-hover:text-slate-200"
          }`}
        />
      </button>

      {/* Apple iOS Liquid Glass Droplet Bloom Dropdown Container */}
      {isOpen && (
        <div
          ref={menuRef}
          className="absolute left-0 right-0 z-[100] mt-2.5 rounded-[28px] liquid-dropdown-menu"
        >
          {/* Large list Search Bar */}
          {options.length >= 8 && (
            <div className="p-2 pb-1.5 border-b border-white/10 relative z-10">
              <div className="relative flex items-center">
                <Search size={13} className="absolute left-3 text-slate-400 pointer-events-none" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setHighlightedIndex(0);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  placeholder="Filter songs or options..."
                  className="w-full rounded-full bg-white/10 hover:bg-white/15 focus:bg-white/20 border border-white/20 pl-8 pr-7 py-1 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-white/50 transition"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSearchQuery("");
                      setHighlightedIndex(0);
                    }}
                    className="absolute right-2 text-slate-400 hover:text-white"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Inner Scrollable List with isolated wheel scrolling */}
          <div
            ref={scrollContainerRef}
            onWheel={(e) => e.stopPropagation()}
            className="max-h-64 sm:max-h-72 overflow-y-auto overflow-x-hidden p-2 space-y-1.5 overscroll-contain liquid-select-scroll"
          >
            {filteredOptions.length === 0 ? (
              <div className="px-4 py-3 text-center text-xs text-slate-400">
                {searchQuery ? "No matching results" : "No options available"}
              </div>
            ) : (
              filteredOptions.map((option, idx) => {
                const isSelected = option.value === value;
                const isHighlighted = idx === highlightedIndex;

                return (
                  <div
                    key={String(option.value)}
                    data-select-item
                    onClick={() => handleSelect(option.value)}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    className={`group/item flex items-center justify-between gap-3 rounded-full px-4 py-2.5 text-xs transition-all duration-200 cursor-pointer liquid-dropdown-item ${
                      isSelected
                        ? "liquid-glass-pill-active"
                        : isHighlighted
                        ? "liquid-glass-pill-hover"
                        : "text-slate-200 border border-transparent hover:text-white"
                    }`}
                    style={{
                      animationDelay: `${Math.min(idx, 5) * 20}ms`,
                    }}
                  >
                    <div className="flex min-w-0 items-center gap-2.5 truncate">
                      {option.icon}
                      <span className="truncate">{option.label}</span>
                    </div>

                    {isSelected && (
                      <div className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-white/30 border border-white/60 text-white shadow-sm shadow-black/40 animate-in zoom-in-75 duration-150">
                        <Check size={11} strokeWidth={2.8} />
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
