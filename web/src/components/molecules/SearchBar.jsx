import { Spinner } from "../atoms/Spinner.jsx";
import { FullscreenCloseIcon, FullscreenOpenIcon } from "../atoms/Icons.jsx";
import { ModeSwitch } from "./ModeSwitch.jsx";
import { FontPicker } from "./FontPicker.jsx";

export function SearchBar({
  mode,
  onModeChange,
  artist,
  title,
  onArtistChange,
  onTitleChange,
  onLoad,
  loading,
  fontIndex,
  onFontChange,
  fullscreen,
  onFullscreen,
}) {
  function onKeyDown(event) {
    if (event.key === "Enter") {
      onLoad();
    }
  }

  return (
    <header className="searchbar" id="searchbar">
      <ModeSwitch mode={mode} onModeChange={onModeChange} />
      <div className="search-fields glass karaoke-tool">
        <input
          id="artist"
          type="text"
          placeholder="Artista"
          autoComplete="off"
          spellCheck="false"
          value={artist}
          onChange={(event) => onArtistChange(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <span className="dot">·</span>
        <input
          id="title"
          type="text"
          placeholder="Canción"
          autoComplete="off"
          spellCheck="false"
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>
      <button id="loadBtn" className="load-btn karaoke-tool" disabled={loading} onClick={onLoad}>
        <span className="load-label" hidden={loading}>Cargar</span>
        <Spinner hidden={!loading} />
      </button>
      <FontPicker fontIndex={fontIndex} onFontChange={onFontChange} />
      <button id="fsBtn" className="icon-btn glass" title="Pantalla completa (F)" onClick={onFullscreen}>
        <FullscreenOpenIcon hidden={fullscreen} />
        <FullscreenCloseIcon hidden={!fullscreen} />
      </button>
    </header>
  );
}
