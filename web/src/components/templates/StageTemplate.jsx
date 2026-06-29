import { Background } from "../atoms/Background.jsx";

export function StageTemplate({ imageUrl, imageReady, children }) {
  return (
    <>
      <Background imageUrl={imageUrl} imageReady={imageReady} />
      <main className="stage">{children}</main>
      <svg className="svg-defs" width="0" height="0" aria-hidden="true" focusable="false">
        <filter id="liquidGlass" x="-35%" y="-35%" width="170%" height="170%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency="0.006 0.009" numOctaves="2" seed="11" result="noise" />
          <feGaussianBlur in="noise" stdDeviation="1.4" result="soft" />
          <feDisplacementMap in="SourceGraphic" in2="soft" scale="34" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </svg>
    </>
  );
}
