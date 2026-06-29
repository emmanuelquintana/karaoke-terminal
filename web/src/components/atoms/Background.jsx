export function Background({ imageUrl, imageReady }) {
  const imageStyle = imageUrl ? { backgroundImage: `url("${imageUrl}")` } : undefined;

  return (
    <>
      <div className="bg-layer">
        <div id="bgImage" className={`bg-image${imageReady ? " ready" : ""}`} style={imageStyle} />
        <div className="bg-blob blob1" />
        <div className="bg-blob blob2" />
        <div className="bg-blob blob3" />
        <div className="bg-blob blob4" />
      </div>
      <div className="bg-tint" />
      <div className="vignette" />
    </>
  );
}
