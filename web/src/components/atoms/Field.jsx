export function Field({ label, children, compact = false, className = "" }) {
  return (
    <label className={`field${compact ? " compact" : ""}${className ? ` ${className}` : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}
