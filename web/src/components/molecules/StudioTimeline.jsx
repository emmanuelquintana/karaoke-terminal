import { formatTime } from "../../constants.js";
import { RangeField } from "../atoms/RangeField.jsx";
import { Spinner } from "../atoms/Spinner.jsx";

export function StudioTimeline({ studio, videoTitle, onStudioChange, onPreview, onExport, downloadUrl }) {
  const duration = studio.duration || 0;
  const maxLength = Math.max(1, Math.floor(Math.min(studio.maxClipSeconds, duration || studio.maxClipSeconds)));
  const maxStart = duration > 0 ? Math.max(0, duration - studio.clipLength) : 1;

  function setClipStart(value) {
    onStudioChange({ ...studio, clipStart: Number(value) });
  }

  function setClipLength(value) {
    onStudioChange({ ...studio, clipLength: Number(value) });
  }

  return (
    <div className="studio-timeline glass">
      <div className="timeline-head">
        <strong id="studioClipLabel">Clip {formatTime(studio.clipStart)} - {formatTime(studio.clipStart + studio.clipLength)}</strong>
        <span id="studioVideoMeta">{videoTitle}{duration ? ` · ${formatTime(duration)}` : ""}</span>
      </div>
      <RangeField
        label="Inicio"
        valueLabel={formatTime(studio.clipStart)}
        inputProps={{
          id: "studioStart",
          min: 0,
          max: maxStart,
          step: 0.1,
          value: studio.clipStart,
          disabled: !studio.prepared,
          onChange: (event) => setClipStart(event.target.value),
        }}
      />
      <RangeField
        label="Duración"
        valueLabel={`${Math.round(studio.clipLength)}s`}
        inputProps={{
          id: "studioLength",
          min: duration < 5 ? 1 : 5,
          max: maxLength,
          step: 1,
          value: studio.clipLength,
          onChange: (event) => setClipLength(event.target.value),
        }}
      />
      <div className="studio-actions">
        <button id="studioPlayClipBtn" className="studio-secondary" disabled={!studio.prepared} onClick={onPreview}>Probar tramo</button>
        <button id="studioExportBtn" className="studio-primary" disabled={!studio.prepared || studio.exporting} onClick={onExport}>
          <span className="studio-export-label" hidden={studio.exporting}>Exportar MP4</span>
          <Spinner hidden={!studio.exporting} />
        </button>
        <a id="studioDownload" className="studio-download" href={downloadUrl || "#"} download hidden={!downloadUrl}>Descargar</a>
      </div>
    </div>
  );
}
