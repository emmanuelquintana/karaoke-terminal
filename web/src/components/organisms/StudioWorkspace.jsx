import { useMemo } from "react";
import { STUDIO_FONT_STACKS, formatTime } from "../../constants.js";
import { StudioPreparePanel, StudioSubtitleControls } from "../molecules/StudioControls.jsx";
import { StudioTimeline } from "../molecules/StudioTimeline.jsx";

function activeStudioLine(lines, time, offset) {
  let match = null;
  for (const line of lines) {
    if ((line.time + offset) <= time + 0.01) {
      match = line;
    } else {
      break;
    }
  }
  if (!match || !match.text || match.text === "♪") return null;
  const lineStart = Number(match.time) + offset;
  const lineEnd = Number(match.end);
  if (Number.isFinite(lineEnd)) {
    const shiftedEnd = lineEnd + offset;
    if (time < lineStart - 0.05 || time > shiftedEnd + 0.18) {
      return null;
    }
  }
  return match;
}

export function StudioWorkspace({
  hidden,
  form,
  preparing,
  studio,
  status,
  syncNote,
  videoTitle,
  videoSrc,
  currentTime,
  downloadUrl,
  videoRef,
  frameRef,
  captionRef,
  onFormChange,
  onPrepare,
  onStudioChange,
  onSync,
  onPreview,
  onExport,
  onVideoMetadata,
  onVideoTimeUpdate,
  onVideoPlay,
  onVideoPause,
}) {
  const captionLine = useMemo(
    () => activeStudioLine(studio.lines, currentTime || studio.clipStart, studio.offset),
    [studio.lines, currentTime, studio.clipStart, studio.offset],
  );
  const captionStyle = {
    fontFamily: STUDIO_FONT_STACKS[studio.font] || STUDIO_FONT_STACKS.Inter,
    fontSize: `${studio.size}px`,
  };

  return (
    <section id="studio" className="studio" hidden={hidden}>
      <div className="studio-copy">
        <StudioPreparePanel
          video={form.video}
          artist={form.artist}
          title={form.title}
          preparing={preparing}
          onVideoChange={(video) => onFormChange({ ...form, video })}
          onArtistChange={(artist) => onFormChange({ ...form, artist })}
          onTitleChange={(title) => onFormChange({ ...form, title })}
          onPrepare={onPrepare}
        />
        <StudioSubtitleControls
          studio={studio}
          status={status}
          syncNote={syncNote}
          onStudioChange={onStudioChange}
          onSync={onSync}
        />
      </div>
      <div className="studio-preview-wrap">
        <div id="studioFrame" ref={frameRef} className={`studio-frame ${studio.format}`}>
          <video
            id="studioPlayer"
            ref={videoRef}
            src={videoSrc || undefined}
            playsInline
            controls
            preload="metadata"
            onLoadedMetadata={onVideoMetadata}
            onTimeUpdate={onVideoTimeUpdate}
            onPlay={onVideoPlay}
            onPause={onVideoPause}
          />
          <div
            id="studioCaption"
            ref={captionRef}
            className={`studio-caption ${studio.position} ${studio.style} ${studio.color}`}
            style={captionStyle}
            hidden={!captionLine}
          >
            {captionLine?.text || ""}
          </div>
          <div id="studioEmpty" className="studio-empty" hidden={studio.prepared}>
            <span>Prepara un video para ver el encuadre</span>
          </div>
        </div>
        <StudioTimeline
          studio={studio}
          videoTitle={videoTitle || "58s max"}
          onStudioChange={onStudioChange}
          onPreview={onPreview}
          onExport={onExport}
          downloadUrl={downloadUrl}
        />
      </div>
    </section>
  );
}
