"use client";

interface SparklineProps {
  data: number[];
  color?: string;
  fill?: boolean;
  height?: number;
}

export function Sparkline({ data, color = "var(--ink)", fill = false, height = 44 }: SparklineProps) {
  if (data.length < 2) return <div style={{ height }} />;
  const w = 200;
  const h = height;
  const pad = 2;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pts: readonly [number, number][] = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / range) * (h - pad * 2);
    return [x, y];
  });
  const first = pts[0]!;
  const last = pts[pts.length - 1]!;
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ");
  const area = `${d} L${last[0]},${h} L${first[0]},${h} Z`;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height }}
    >
      {fill && <path d={area} fill={color} opacity="0.08" />}
      <path d={d} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill={color} />
    </svg>
  );
}

interface DonutSegment {
  value: number;
  color: string;
}

export function Donut({ segments, size = 140 }: { segments: DonutSegment[]; size?: number }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r = size / 2 - 12;
  const cx = size / 2;
  const cy = size / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--sand)" strokeWidth="14" />
      {segments.map((s, i) => {
        const len = (s.value / total) * c;
        const dash = `${len} ${c - len}`;
        const dashOffset = -offset;
        offset += len;
        return (
          <circle
            key={i}
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={s.color}
            strokeWidth="14"
            strokeDasharray={dash}
            strokeDashoffset={dashOffset}
            strokeLinecap="butt"
            transform={`rotate(-90 ${cx} ${cy})`}
          />
        );
      })}
    </svg>
  );
}

interface FlowStreamProps {
  inflow?: number[];
  outflow?: number[];
}

// Stacked area chart of money in vs money out. Defaults to the design mock
// series so callers that don't have real data yet still render something.
export function FlowStream({
  inflow = [42, 48, 51, 58, 62, 68, 74, 79, 85, 91, 96, 104],
  outflow = [38, 42, 44, 49, 52, 55, 58, 62, 64, 66, 68, 71],
}: FlowStreamProps) {
  const w = 560;
  const h = 180;
  const max = Math.max(...inflow, ...outflow, 1) * 1.15;
  const pts = (arr: number[]) =>
    arr.map((v, i) => {
      const x = (i / (arr.length - 1)) * w;
      const y = h - (v / max) * h;
      return [x, y] as const;
    });
  const toPath = (p: readonly (readonly [number, number])[]) =>
    p.map((pt, i) => `${i === 0 ? "M" : "L"}${pt[0]},${pt[1]}`).join(" ");
  const incPts = pts(inflow);
  const expPts = pts(outflow);
  const incArea = `${toPath(incPts)} L${w},${h} L0,${h} Z`;
  const expArea = `${toPath(expPts)} L${w},${h} L0,${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 180, display: "block" }}>
      {[0, 1, 2, 3].map((i) => (
        <line
          key={i}
          x1="0"
          x2={w}
          y1={((i + 1) * h) / 4}
          y2={((i + 1) * h) / 4}
          stroke="var(--rule)"
          strokeDasharray="2 3"
        />
      ))}
      <path d={incArea} fill="var(--sage)" opacity="0.18" />
      <path d={toPath(incPts)} fill="none" stroke="var(--sage)" strokeWidth="2" />
      <path d={expArea} fill="var(--terracotta)" opacity="0.14" />
      <path
        d={toPath(expPts)}
        fill="none"
        stroke="var(--terracotta)"
        strokeWidth="2"
        strokeDasharray="4 3"
      />
      {incPts.map((p, i) => (
        <circle
          key={`i${i}`}
          cx={p[0]}
          cy={p[1]}
          r="2.5"
          fill="var(--paper)"
          stroke="var(--sage)"
          strokeWidth="1.5"
        />
      ))}
    </svg>
  );
}
