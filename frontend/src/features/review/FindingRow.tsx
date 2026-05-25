"use client";

import { useState } from "react";
import type { Finding, ReviewStatus } from "@/domain/finding";
import { PillarTag } from "@/ui/PillarTag";
import { StatusBadge } from "@/ui/StatusBadge";
import { ConfidenceMeter } from "@/ui/ConfidenceMeter";

interface Props {
  finding: Finding;
  onReview: (id: string, status: ReviewStatus) => void;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function FindingRow({ finding, onReview }: Props) {
  const [open, setOpen] = useState(false);
  const panelId = `detail-${finding.id}`;

  return (
    <article className={`finding ${open ? "finding--open" : ""}`}>
      <button
        type="button"
        className="finding__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
      >
        <span className="finding__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="finding__primary">
          <span className="finding__title">{finding.title}</span>
          <span className="finding__cite">
            {finding.jurisdiction} · {finding.documentTitle}, {finding.articleNumber}
            {finding.language !== "en" && (
              <span className="finding__lang" title={`Source language: ${finding.language}`}>
                {finding.language.toUpperCase()}
              </span>
            )}
          </span>
        </span>
        <PillarTag pillar={finding.pillar} />
        <span className="finding__indicator" title={finding.indicatorLabel}>
          {finding.indicator}
        </span>
        <ConfidenceMeter value={finding.confidence} />
        <StatusBadge status={finding.reviewStatus} />
      </button>

      {open && (
        <div className="finding__detail" id={panelId}>
          <dl className="fields">
            <Field label="Scope">{finding.scope}</Field>
            <Field label="Provisions">{finding.provisions}</Field>
            <Field label="Impact">{finding.impact}</Field>
            <Field label="Indicator">
              {finding.indicator} — {finding.indicatorLabel}
            </Field>
            <Field label="Last update">{formatDate(finding.lastUpdate)}</Field>
            <Field label="Source">
              <a href={finding.url} target="_blank" rel="noreferrer noopener">
                {finding.articleNumber} ↗
              </a>
            </Field>
          </dl>

          <div className="finding__actions">
            <button
              type="button"
              className="btn btn--verify"
              onClick={() => onReview(finding.id, "verified")}
              disabled={finding.reviewStatus === "verified"}
            >
              ✓ Verify
            </button>
            <button
              type="button"
              className="btn btn--reject"
              onClick={() => onReview(finding.id, "rejected")}
              disabled={finding.reviewStatus === "rejected"}
            >
              ✕ Reject
            </button>
            <button
              type="button"
              className="btn btn--reset"
              onClick={() => onReview(finding.id, "pending")}
              disabled={finding.reviewStatus === "pending"}
            >
              ↺ Reset
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="fields__row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
