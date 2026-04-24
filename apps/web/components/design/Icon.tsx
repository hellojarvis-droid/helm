import type { ReactElement, SVGProps } from "react";

export type IconName =
  | "home"
  | "megaphone"
  | "book"
  | "receipt"
  | "chart"
  | "folder"
  | "settings"
  | "users"
  | "bell"
  | "search"
  | "plus"
  | "send"
  | "sparkle"
  | "arrowUp"
  | "arrowDown"
  | "check"
  | "play"
  | "pause"
  | "more"
  | "close"
  | "image"
  | "video"
  | "card"
  | "target"
  | "tweaks"
  | "shield";

const PATHS: Record<IconName, ReactElement> = {
  home: <path d="M3 10l7-6 7 6v8a1 1 0 0 1-1 1h-3v-6H7v6H4a1 1 0 0 1-1-1v-8z" />,
  megaphone: <path d="M3 10v2a1 1 0 0 0 1 1h1l2 4h2l-1-4h2l6 3V5l-6 3H4a1 1 0 0 0-1 1v1z" />,
  book: (
    <>
      <path d="M4 3h7a3 3 0 0 1 3 3v11H7a3 3 0 0 0-3 3V3z" />
      <path d="M14 6h3v14h-8" />
    </>
  ),
  receipt: (
    <>
      <path d="M5 3h10v15l-2-1-2 1-2-1-2 1-2-1V3z" />
      <path d="M8 7h5M8 10h5M8 13h3" />
    </>
  ),
  chart: (
    <>
      <path d="M3 17V3M3 17h14" />
      <rect x="6" y="10" width="2" height="6" />
      <rect x="10" y="6" width="2" height="10" />
      <rect x="14" y="12" width="2" height="4" />
    </>
  ),
  folder: <path d="M3 6a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6z" />,
  settings: (
    <>
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 3v2M10 15v2M17 10h-2M5 10H3M15 5l-1.4 1.4M6.4 13.6L5 15M15 15l-1.4-1.4M6.4 6.4L5 5" />
    </>
  ),
  users: (
    <>
      <circle cx="7" cy="7" r="3" />
      <circle cx="14" cy="8" r="2" />
      <path d="M2 16c0-2.5 2.5-4 5-4s5 1.5 5 4M12 15c.5-2 2-3 4-3s4 1 4 3" />
    </>
  ),
  bell: (
    <>
      <path d="M5 14V9a5 5 0 0 1 10 0v5l2 2H3l2-2z" />
      <path d="M8 17a2 2 0 0 0 4 0" />
    </>
  ),
  search: (
    <>
      <circle cx="9" cy="9" r="5" />
      <path d="M13 13l4 4" />
    </>
  ),
  plus: <path d="M10 4v12M4 10h12" />,
  send: <path d="M3 10l14-6-6 14-2-6-6-2z" />,
  sparkle: <path d="M10 2v4M10 14v4M2 10h4M14 10h4M5 5l2 2M13 13l2 2M15 5l-2 2M7 13l-2 2" />,
  arrowUp: <path d="M10 16V4M5 9l5-5 5 5" />,
  arrowDown: <path d="M10 4v12M5 11l5 5 5-5" />,
  check: <path d="M4 10l4 4 8-8" />,
  play: <path d="M6 4l10 6-10 6V4z" />,
  pause: (
    <>
      <rect x="5" y="4" width="3" height="12" />
      <rect x="12" y="4" width="3" height="12" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="10" r="1" />
      <circle cx="10" cy="10" r="1" />
      <circle cx="15" cy="10" r="1" />
    </>
  ),
  close: <path d="M5 5l10 10M15 5L5 15" />,
  image: (
    <>
      <rect x="3" y="4" width="14" height="12" rx="1" />
      <circle cx="7" cy="8" r="1.5" />
      <path d="M3 14l4-4 4 4 3-3 3 3" />
    </>
  ),
  video: (
    <>
      <rect x="3" y="5" width="11" height="10" rx="1" />
      <path d="M14 8l4-2v8l-4-2z" />
    </>
  ),
  card: (
    <>
      <rect x="3" y="5" width="14" height="10" rx="1" />
      <path d="M3 9h14" />
    </>
  ),
  target: (
    <>
      <circle cx="10" cy="10" r="6" />
      <circle cx="10" cy="10" r="3" />
      <circle cx="10" cy="10" r="1" fill="currentColor" />
    </>
  ),
  tweaks: (
    <>
      <circle cx="6" cy="6" r="2" />
      <circle cx="14" cy="14" r="2" />
      <path d="M6 8v8M14 4v8" />
    </>
  ),
  shield: <path d="M10 2l6 2v6c0 4-3 7-6 8-3-1-6-4-6-8V4l6-2z" />,
};

interface Props extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 16, ...props }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {PATHS[name]}
    </svg>
  );
}
