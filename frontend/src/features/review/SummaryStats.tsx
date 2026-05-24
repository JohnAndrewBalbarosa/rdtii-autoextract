import type { Finding } from "@/domain/finding";

export function SummaryStats({ findings }: { findings: Finding[] }) {
  const total = findings.length;
  const pending = findings.filter((f) => f.reviewStatus === "pending").length;
  const verified = findings.filter((f) => f.reviewStatus === "verified").length;
  const rejected = findings.filter((f) => f.reviewStatus === "rejected").length;
  const reviewed = verified + rejected;
  const progress = total === 0 ? 0 : Math.round((reviewed / total) * 100);

  return (
    <dl className="summary">
      <div className="summary__item summary__item--accent">
        <dt>Awaiting review</dt>
        <dd>{pending}</dd>
      </div>
      <div className="summary__item">
        <dt>Verified</dt>
        <dd>{verified}</dd>
      </div>
      <div className="summary__item">
        <dt>Rejected</dt>
        <dd>{rejected}</dd>
      </div>
      <div className="summary__item summary__item--progress">
        <dt>Human-validated</dt>
        <dd>
          {progress}%
          <div className="summary__bar" aria-hidden="true">
            <span style={{ width: `${progress}%` }} />
          </div>
        </dd>
      </div>
    </dl>
  );
}
