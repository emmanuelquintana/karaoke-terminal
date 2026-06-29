export function Toast({ message }) {
  return (
    <div id="toast" className="toast" hidden={!message}>
      {message}
    </div>
  );
}
