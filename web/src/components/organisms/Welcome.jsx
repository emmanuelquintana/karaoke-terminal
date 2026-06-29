import { SUGGESTIONS } from "../../constants.js";

export function Welcome({ onSuggestion }) {
  return (
    <section id="welcome" className="welcome">
      <div className="welcome-glow" />
      <h1>Terminal&nbsp;Karaoke</h1>
      <p>Escribe un artista y una canción para encender el escenario.</p>
      <p className="suggest-label">O prueba con una sugerencia:</p>
      <div className="suggestions" id="suggestions">
        {SUGGESTIONS.map((suggestion) => (
          <button key={`${suggestion.artist}-${suggestion.title}`} className="chip" onClick={() => onSuggestion(suggestion)}>
            {suggestion.artist} — {suggestion.title}
          </button>
        ))}
      </div>
      <div className="preview">
        <div className="preview-card glass">
          <div className="preview-cover">♪</div>
          <div className="preview-meta">
            <strong>Tu canción</strong>
            <span>Tu artista</span>
            <i className="preview-bar"><b /></i>
          </div>
        </div>
        <div className="preview-lyrics">
          <p>Una vista previa</p>
          <p>de cómo se ve la letra</p>
          <p>iluminándose contigo</p>
        </div>
      </div>
    </section>
  );
}
