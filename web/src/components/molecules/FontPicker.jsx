import { useEffect, useRef, useState } from "react";
import { LYRIC_FONTS } from "../../constants.js";

export function FontPicker({ fontIndex, onFontChange }) {
  const [open, setOpen] = useState(false);
  const pickerRef = useRef(null);
  const activeFont = LYRIC_FONTS[fontIndex] || LYRIC_FONTS[0];

  useEffect(() => {
    function onDocumentClick(event) {
      if (!pickerRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("click", onDocumentClick);
    return () => document.removeEventListener("click", onDocumentClick);
  }, []);

  return (
    <div className="font-picker karaoke-tool" id="fontPicker" ref={pickerRef}>
      <button
        id="fontBtn"
        className="font-toggle glass"
        title="Fuente de la letra"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
      >
        <span className="ic-font">Aa</span>
        <span id="fontCurrent" className="font-current">{activeFont.name}</span>
        <span className="caret">▾</span>
      </button>
      <div className="font-menu glass" id="fontMenu" hidden={!open} role="listbox">
        {LYRIC_FONTS.map((font, index) => (
          <button
            key={font.name}
            className={`font-option${index === fontIndex ? " active" : ""}`}
            style={{ fontFamily: font.stack }}
            onClick={() => {
              onFontChange(index);
              setOpen(false);
            }}
          >
            <span>{font.name}</span>
            <span className="tick">✓</span>
          </button>
        ))}
      </div>
    </div>
  );
}
