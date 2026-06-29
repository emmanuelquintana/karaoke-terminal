import { MusicIcon, StudioIcon } from "../atoms/Icons.jsx";

export function ModeSwitch({ mode, onModeChange }) {
  return (
    <nav className="mode-switch glass" aria-label="Modo de trabajo">
      <button
        id="karaokeModeBtn"
        className={`mode-btn${mode === "karaoke" ? " active" : ""}`}
        title="Karaoke"
        onClick={() => onModeChange("karaoke")}
      >
        <MusicIcon />
        <span>Karaoke</span>
      </button>
      <button
        id="studioModeBtn"
        className={`mode-btn${mode === "studio" ? " active" : ""}`}
        title="Estudio TikTok"
        onClick={() => onModeChange("studio")}
      >
        <StudioIcon />
        <span>Estudio</span>
      </button>
    </nav>
  );
}
