import { Field } from "../atoms/Field.jsx";
import { RangeField } from "../atoms/RangeField.jsx";
import { Spinner } from "../atoms/Spinner.jsx";
import { SyncIcon } from "../atoms/Icons.jsx";

export function StudioPreparePanel({
  video,
  artist,
  title,
  preparing,
  onVideoChange,
  onArtistChange,
  onTitleChange,
  onPrepare,
}) {
  function onKeyDown(event) {
    if (event.key === "Enter") onPrepare();
  }

  return (
    <div className="studio-panel glass">
      <span className="studio-kicker">Estudio TikTok</span>
      <h1>Video con letra sincronizada</h1>
      <p className="studio-note">Busca el video, elige la canción y ajusta el tramo exacto para exportar un clip de hasta 58 segundos.</p>
      <div className="studio-form">
        <Field label="Video">
          <input id="studioVideo" type="text" placeholder="URL de YouTube o búsqueda del video oficial" autoComplete="off" spellCheck="false" value={video} onChange={(event) => onVideoChange(event.target.value)} onKeyDown={onKeyDown} />
        </Field>
        <div className="field-row">
          <Field label="Artista">
            <input id="studioArtist" type="text" placeholder="Artista" autoComplete="off" spellCheck="false" value={artist} onChange={(event) => onArtistChange(event.target.value)} onKeyDown={onKeyDown} />
          </Field>
          <Field label="Canción">
            <input id="studioTitle" type="text" placeholder="Canción" autoComplete="off" spellCheck="false" value={title} onChange={(event) => onTitleChange(event.target.value)} onKeyDown={onKeyDown} />
          </Field>
        </div>
        <button id="studioPrepareBtn" className="studio-primary" disabled={preparing} onClick={onPrepare}>
          <span className="studio-prepare-label" hidden={preparing}>Preparar estudio</span>
          <Spinner hidden={!preparing} />
        </button>
      </div>
    </div>
  );
}

export function StudioSubtitleControls({ studio, status, syncNote, onStudioChange, onSync }) {
  const set = (patch) => onStudioChange({ ...studio, ...patch });

  return (
    <div className="studio-panel glass studio-controls-panel">
      <div className="studio-panel-head">
        <span className="studio-kicker">Subtítulos</span>
        <strong id="studioStatus">{status}</strong>
      </div>
      <div className="segmented" id="formatGroup" aria-label="Formato">
        <button className={`seg${studio.format === "vertical" ? " active" : ""}`} data-format="vertical" onClick={() => set({ format: "vertical" })}>Vertical</button>
        <button className={`seg${studio.format === "horizontal" ? " active" : ""}`} data-format="horizontal" onClick={() => set({ format: "horizontal" })}>Horizontal</button>
      </div>
      <div className="control-grid">
        <Field label="Fuente" compact>
          <select id="studioFont" value={studio.font} onChange={(event) => set({ font: event.target.value })}>
            <option value="Inter">Inter</option>
            <option value="Poppins">Poppins</option>
            <option value="Playfair">Playfair</option>
            <option value="Caveat">Caveat</option>
            <option value="Arial">Arial</option>
          </select>
        </Field>
        <Field label="Posición" compact>
          <select id="studioPosition" value={studio.position} onChange={(event) => set({ position: event.target.value })}>
            <option value="bottom">Abajo</option>
            <option value="middle">Centro</option>
            <option value="top">Arriba</option>
          </select>
        </Field>
        <Field label="Estilo" compact>
          <select id="studioStyle" value={studio.style} onChange={(event) => set({ style: event.target.value })}>
            <option value="boxed">Caja</option>
            <option value="karaoke">Karaoke</option>
            <option value="minimal">Limpio</option>
          </select>
        </Field>
        <Field label="Color" compact>
          <select id="studioColor" value={studio.color} onChange={(event) => set({ color: event.target.value })}>
            <option value="white">Blanco</option>
            <option value="warm">Cálido</option>
            <option value="rose">Rosa</option>
          </select>
        </Field>
      </div>
      <RangeField label="Tamaño" valueLabel={`${studio.size}px`} inputProps={{ id: "studioSize", min: 28, max: 96, step: 1, value: studio.size, onChange: (event) => set({ size: Number(event.target.value) }) }} />
      <RangeField label="Desfase letra" valueLabel={`${studio.offset.toFixed(1)}s`} inputProps={{ id: "studioOffset", min: -60, max: 180, step: 0.1, value: studio.offset, onChange: (event) => set({ offset: Number(event.target.value) }) }} />
      <div className="studio-sync-row">
        <button id="studioSyncBtn" className="studio-secondary studio-sync-btn" disabled={!studio.prepared || studio.syncing} onClick={onSync}>
          <SyncIcon />
          <span className="studio-sync-label" hidden={studio.syncing}>Sincronizar audio</span>
          <Spinner hidden={!studio.syncing} />
        </button>
        <p id="studioSyncNote" className="studio-sync-note">{syncNote}</p>
      </div>
    </div>
  );
}
