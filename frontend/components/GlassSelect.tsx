"use client";

import { useEffect, useRef, useState, ReactNode } from "react";
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
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

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

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const handleSelect = (val: T) => {
    onChange(val);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={`relative w-full ${isOpen ? "z-50" : "z-10"} ${className}`}>
      {/* Oval Shaped Glass Tile Trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setIsOpen((prev) => !prev)}
        className={`group flex w-full items-center justify-between gap-2.5 rounded-full px-4 py-2.5 text-xs sm:text-sm font-medium transition-all duration-200 outline-none ${
          isOpen
            ? "border border-[#00CEC8]/60 shadow-[0_0_0_2px_rgba(0,206,200,0.22),inset_0_1.5px_1px_rgba(255,255,255,0.28)]"
            : "border border-white/12 hover:border-white/25 shadow-[inset_0_1.5px_1px_rgba(255,255,255,0.2),0_8px_20px_-4px_rgba(0,0,0,0.45)]"
        } ${
          disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"
        }`}
        style={{
          background:
            "linear-gradient(145deg, rgba(255, 255, 255, 0.09) 0%, rgba(255, 255, 255, 0.02) 45%, rgba(18, 22, 32, 0.45) 100%), rgba(20, 24, 34, 0.52)",
          backdropFilter: "blur(24px) saturate(190%)",
          WebkitBackdropFilter: "blur(24px) saturate(190%)",
        }}
      >
        <div className="flex min-w-0 items-center gap-2 truncate">
          {selectedOption?.icon}
          <span className={`truncate ${selectedOption ? "text-slate-100 font-semibold" : "text-slate-400"}`}>
            {selectedOption ? selectedOption.label : placeholder}
          </span>
        </div>

        <ChevronDown
          size={16}
          className={`shrink-0 transition-transform duration-200 ${
            isOpen ? "rotate-180 text-[#00CEC8]" : "text-slate-400 group-hover:text-slate-200"
          }`}
        />
      </button>

      {/* Floating Frosted Glass Dropdown Menu (No OS blue highlight) */}
      {isOpen && (
        <div
          className="absolute left-0 right-0 z-[100] mt-1.5 max-h-60 overflow-y-auto rounded-2xl p-1.5 space-y-1 border border-white/14 animate-in fade-in zoom-in-95 duration-150"
          style={{
            background:
              "linear-gradient(140deg, rgba(255, 255, 255, 0.08) 0%, rgba(18, 22, 32, 0.95) 35%, rgba(11, 14, 20, 0.98) 100%)",
            backdropFilter: "blur(40px) saturate(210%)",
            WebkitBackdropFilter: "blur(40px) saturate(210%)",
            boxShadow:
              "0 25px 60px -10px rgba(0, 0, 0, 0.92), inset 0 1.5px 1px rgba(255, 255, 255, 0.25), 0 0 0 1px rgba(255, 255, 255, 0.06)",
          }}
        >
          {options.length === 0 ? (
            <div className="px-3 py-2 text-center text-xs text-slate-400">No options available</div>
          ) : (
            options.map((option) => {
              const isSelected = option.value === value;
              return (
                <div
                  key={String(option.value)}
                  onClick={() => handleSelect(option.value)}
                  className={`group flex items-center justify-between gap-2 rounded-xl px-3.5 py-2 text-xs transition-all duration-150 cursor-pointer ${
                    isSelected
                      ? "text-white font-semibold border border-[#00CEC8]/45 shadow-[inset_0_1px_1.5px_rgba(252,239,195,0.25),0_4px_12px_rgba(0,0,0,0.35)]"
                      : "text-slate-300 hover:text-white hover:border hover:border-white/14 hover:shadow-[inset_0_1px_1px_rgba(255,255,255,0.18)]"
                  }`}
                  style={
                    isSelected
                      ? {
                          background:
                            "linear-gradient(135deg, rgba(0, 206, 200, 0.22) 0%, rgba(252, 239, 195, 0.08) 100%), rgba(16, 28, 44, 0.85)",
                          backdropFilter: "blur(16px)",
                          WebkitBackdropFilter: "blur(16px)",
                        }
                      : {
                          background: "transparent",
                        }
                  }
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.background =
                        "linear-gradient(135deg, rgba(255, 255, 255, 0.10) 0%, rgba(255, 255, 255, 0.02) 100%), rgba(28, 35, 48, 0.55)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.background = "transparent";
                    }
                  }}
                >
                  <div className="flex min-w-0 items-center gap-2 truncate">
                    {option.icon}
                    <span className="truncate">{option.label}</span>
                  </div>

                  {isSelected && (
                    <div className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-[#00CEC8] text-[#032023] shadow-sm shadow-[#00CEC8]/50">
                      <Check size={11} strokeWidth={3} />
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

