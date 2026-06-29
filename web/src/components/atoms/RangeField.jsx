export function RangeField({ label, valueLabel, inputProps }) {
  return (
    <label className="range-field">
      <span>
        {label} <b>{valueLabel}</b>
      </span>
      <input type="range" {...inputProps} />
    </label>
  );
}
