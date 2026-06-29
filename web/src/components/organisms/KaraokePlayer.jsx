import { useEffect, useRef } from "react";
import { SeekBar } from "../molecules/SeekBar.jsx";
import { KaraokeControls } from "../molecules/KaraokeControls.jsx";

export function KaraokePlayer({
  hidden,
  song,
  lines,
  activeIndex,
  coverUrl,
  coverReady,
  audioNote,
  currentTime,
  duration,
  playingState,
  volume,
  onLineClick,
  onSeek,
  onToggle,
  onBack,
  onForward,
  onVolumeChange,
  onCoverLoad,
  onCoverError,
}) {
  const progress = duration > 0 ? Math.max(0, Math.min(1, currentTime / duration)) : 0;
  const lyricsRef = useRef(null);

  useEffect(() => {
    const pane = lyricsRef.current;
    const active = pane?.querySelector(".line.active");
    if (!pane) return;
    if (active) {
      const target = active.offsetTop - pane.clientHeight * 0.42 + active.clientHeight / 2;
      pane.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
    } else {
      pane.scrollTo({ top: 0, behavior: "auto" });
    }
  }, [activeIndex]);

  return (
    <section id="player" className="player" hidden={hidden}>
      <aside className="now-playing glass">
        <div className="cover-wrap">
          <img id="cover" className={`cover${coverReady ? " ready" : ""}`} alt="" src={coverUrl || undefined} crossOrigin="anonymous" onLoad={onCoverLoad} onError={onCoverError} />
          <div className="cover-fallback" id="coverFallback" style={{ display: coverReady ? "none" : "flex" }}>♪</div>
        </div>
        <div className="meta">
          <h2 id="songTitle" className="song-title">{song?.title || ""}</h2>
          <p id="songArtist" className="song-artist">{song?.artist || ""}</p>
          <span id="songMode" className="badge">{song?.mode || ""}</span>
        </div>
        <SeekBar current={currentTime} duration={duration} progress={progress} onSeek={onSeek} />
        <KaraokeControls playingState={playingState} onBack={onBack} onToggle={onToggle} onForward={onForward} />
        <div className="volume">
          <span className="vol-ic">🔊</span>
          <input id="volume" type="range" min="0" max="1" step="0.01" value={volume} onChange={(event) => onVolumeChange(Number(event.target.value))} />
        </div>
        <p id="audioNote" className="audio-note" hidden={!audioNote}>{audioNote}</p>
      </aside>
      <div className="lyrics-pane">
        <div id="lyrics" className="lyrics" ref={lyricsRef}>
          {lines.length ? lines.map((line, index) => {
            const distance = index - activeIndex;
            const activeClass = distance === 0 ? "active" : distance < 0 ? "past" : distance <= 2 ? "near" : "far";
            const instrumental = line.text === "♪" || line.text === "";
            return (
              <div
                key={`${line.time}-${index}-${line.text}`}
                className={`line ${activeClass}${instrumental ? " instrumental" : ""}`}
                onClick={() => onLineClick(line.time)}
              >
                {line.text || "♪"}
              </div>
            );
          }) : <div className="line">Sin letra disponible.</div>}
        </div>
        <div className="fade-top" />
        <div className="fade-bottom" />
      </div>
    </section>
  );
}
