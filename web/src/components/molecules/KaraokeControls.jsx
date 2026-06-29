import { PauseIcon, PlayIcon } from "../atoms/Icons.jsx";

export function KaraokeControls({ playingState, onBack, onToggle, onForward }) {
  return (
    <div className="controls">
      <button id="backBtn" className="ctrl ghost" title="Retroceder 5s" onClick={onBack}>⟲</button>
      <button id="playBtn" className="ctrl play" title="Reproducir / Pausar" onClick={onToggle}>
        <PlayIcon hidden={playingState !== "paused"} />
        <PauseIcon hidden={playingState !== "playing"} />
        <span className="ic-loading" hidden={playingState !== "loading"} />
      </button>
      <button id="fwdBtn" className="ctrl ghost" title="Adelantar 5s" onClick={onForward}>⟳</button>
    </div>
  );
}
