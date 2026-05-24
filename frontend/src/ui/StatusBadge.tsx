import type { ReviewStatus } from "@/domain/finding";

const LABEL: Record<ReviewStatus, string> = {
  pending: "Pending review",
  verified: "Verified",
  rejected: "Rejected",
};

export function StatusBadge({ status }: { status: ReviewStatus }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      {LABEL[status]}
    </span>
  );
}
