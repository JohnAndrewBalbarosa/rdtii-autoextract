/** Confidence as a small calibrated bar. Low confidence is visually flagged for review priority. */
export function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const level = value >= 0.8 ? "high" : value >= 0.65 ? "mid" : "low";
  return (
    <div className="confidence" title={`Model confidence: ${pct}%`}>
      <div className="confidence__track">
        <div
          className={`confidence__fill confidence__fill--${level}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="confidence__num">{pct}%</span>
    </div>
  );
}
