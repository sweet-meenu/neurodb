// Small hand-rolled icon set (no icon library dependency) — consistent
// 20x20 outline style used by the project sidebar.
type IconProps = { className?: string };

const base = "h-5 w-5 shrink-0";

export function IconHome({ className = base }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 9.5 10 3l7 6.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 8.5V16a1 1 0 0 0 1 1h3v-4a1 1 0 0 1 1-1h0a1 1 0 0 1 1 1v4h3a1 1 0 0 0 1-1V8.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconDatabase({ className = base }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <ellipse cx="10" cy="5" rx="6" ry="2.5" />
      <path d="M4 5v10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V5" strokeLinecap="round" />
      <path d="M4 10c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5" strokeLinecap="round" />
    </svg>
  );
}

export function IconFolder({ className = base }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 6a1 1 0 0 1 1-1h4l1.5 2H16a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6Z" strokeLinejoin="round" />
    </svg>
  );
}

export function IconTerminal({ className = base }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="4" width="14" height="12" rx="1.5" />
      <path d="M6.5 8 9 10.5 6.5 13" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10.5 13h3" strokeLinecap="round" />
    </svg>
  );
}

export function IconHistory({ className = base }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 10a7 7 0 1 0 2.1-5" strokeLinecap="round" />
      <path d="M3 4v4h4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 6.5V10l2.5 1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconArrowLeft({ className = "h-4 w-4 shrink-0" }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M12 15 7 10l5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconImage({ className = base }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="4" width="14" height="12" rx="1.5" />
      <circle cx="7.5" cy="8.5" r="1.25" />
      <path d="M4 15l4.5-4.5 3 3L16 9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconAudio({ className = base }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M7 8v4a1 1 0 0 0 1 1h1.5l3 2.5v-11L9.5 7H8a1 1 0 0 0-1 1Z" strokeLinejoin="round" />
      <path d="M14 7.5a4 4 0 0 1 0 5" strokeLinecap="round" />
    </svg>
  );
}
