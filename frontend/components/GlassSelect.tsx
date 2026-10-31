"use client";

import { useEffect, useRef, useState, ReactNode, KeyboardEvent as ReactKeyboardEvent } from "react";
import { Check, ChevronDown } from "lucide-react";

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
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const selectedIndex = options.findIndex((opt) => opt.value === value);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  // Sync highlightedIndex with selectedIndex when opening
  useEffect(() => {
    if (isOpen) {
      setHighlightedIndex(selectedIndex >= 0 ? selectedIndex : 0);
    }
  }, [isOpen, selectedIndex]);

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

  // Scroll highlighted item into view if navigating with keyboard
  useEffect(() => {
    if (isOpen && menuRef.current && highlightedIndex >= 0) {
      const items = menuRef.current.querySelectorAll<HTMLElement>("[data-select-item]");
      const currentItem = items[highlightedIndex];
      if (currentItem) {
        currentItem.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
  }, [isOpen, highlightedIndex]);

  const handleSelect = (val: T) => {
    onChange(val);
    setIsOpen(false);
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
        setHighlightedIndex((prev) => (prev + 1 < options.length ? prev + 1 : 0));
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((prev) => (prev - 1 >= 0 ? prev - 1 : options.length - 1));
        break;
      case "Home":
        e.preventDefault();
        setHighlightedIndex(0);
        break;
      case "End":
        e.preventDefault();
        setHighlightedIndex(options.length - 1);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < options.length) {
          handleSelect(options[highlightedIndex].value);
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

      {/* Apple iOS Liquid Glass Droplet Bloom Dropdown (Faithful to Sample Images & Video) */}
      {isOpen && (
        <div
          ref={menuRef}
          className="absolute left-0 right-0 z-[100] mt-2.5 max-h-64 overflow-y-auto rounded-[28px] p-2 space-y-1.5 liquid-dropdown-menu"
        >
          {options.length === 0 ? (
            <div className="px-4 py-3 text-center text-xs text-slate-400">No options available</div>
          ) : (
            options.map((option, idx) => {
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
                    animationDelay: `${idx * 28}ms`,
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
      )}
    </div>
  );
}
