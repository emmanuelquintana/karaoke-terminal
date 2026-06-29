export function MusicIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 18V5l11-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="17" cy="16" r="3" />
    </svg>
  );
}

export function StudioIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h10a4 4 0 0 1 0 8H8" />
      <path d="M4 15h5a3 3 0 0 1 0 6H4" />
      <path d="M18 7l3-3M18 15l3 3" />
    </svg>
  );
}

export function FullscreenOpenIcon({ hidden = false }) {
  return (
    <svg className="ic-fs-open" viewBox="0 0 24 24" hidden={hidden} aria-hidden="true">
      <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
    </svg>
  );
}

export function FullscreenCloseIcon({ hidden = false }) {
  return (
    <svg className="ic-fs-close" viewBox="0 0 24 24" hidden={hidden} aria-hidden="true">
      <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />
    </svg>
  );
}

export function PlayIcon({ hidden = false }) {
  return (
    <svg viewBox="0 0 24 24" className="ic-play" hidden={hidden} aria-hidden="true">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

export function PauseIcon({ hidden = false }) {
  return (
    <svg viewBox="0 0 24 24" className="ic-pause" hidden={hidden} aria-hidden="true">
      <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
    </svg>
  );
}

export function SyncIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 12a8 8 0 0 1 13.6-5.7" />
      <path d="M18 3v5h-5" />
      <path d="M20 12a8 8 0 0 1-13.6 5.7" />
      <path d="M6 21v-5h5" />
    </svg>
  );
}
