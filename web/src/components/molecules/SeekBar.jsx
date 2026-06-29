import { formatTime } from "../../constants.js";

export function SeekBar({ current, duration, progress, onSeek }) {
  function eventToTime(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    return ratio * duration;
  }

  return (
    <div className="seek">
      <span id="curTime" className="time">{formatTime(current)}</span>
      <div
        className="track"
        id="track"
        onPointerDown={(event) => onSeek(eventToTime(event))}
        onPointerMove={(event) => {
          if (event.buttons === 1) onSeek(eventToTime(event));
        }}
      >
        <div className="track-fill" id="trackFill" style={{ width: `${progress * 100}%` }} />
        <div className="track-knob" id="trackKnob" style={{ left: `${progress * 100}%` }} />
      </div>
      <span id="durTime" className="time">{formatTime(duration)}</span>
    </div>
  );
}
