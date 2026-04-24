"use client";

// Magnific-style evocative slider. No "CFG 7.5" — human labels like
// "Creativity" / "HDR" / "Resemblance" / "Fractality" with hover help.

export function MagnificSlider({
  label,
  helper,
  min,
  max,
  step = 1,
  value,
  onChange,
  suffix,
  disabled,
}: {
  label: string;
  helper: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
  suffix?: string;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-[0.06em] text-ink-3">
          {label}
        </span>
        <span className="font-mono tabular text-[12px] text-ink-2">
          {value}
          {suffix ?? ""}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-terracotta"
      />
      <p className="mt-0.5 text-[10px] text-ink-3">{helper}</p>
    </label>
  );
}
