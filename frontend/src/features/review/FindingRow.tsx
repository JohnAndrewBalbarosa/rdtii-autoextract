"use client";

import { useEffect, useState } from "react";
import type { Finding, FindingUpdate, ReviewStatus } from "@/domain/finding";
import { PillarTag } from "@/ui/PillarTag";
import { StatusBadge } from "@/ui/StatusBadge";
import { ConfidenceMeter } from "@/ui/ConfidenceMeter";

interface Props {
  finding: Finding;
  onReview: (id: string, status: ReviewStatus) => void;
  onModify: (id: string, patch: FindingUpdate) => Promise<void>;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function FindingRow({ finding, onReview, onModify }: Props) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    title: finding.title,
    scope: finding.scope,
    provisions: finding.provisions,
    impact: finding.impact,
    articleNumber: finding.articleNumber,
    notes: finding.notes,
  });
  const panelId = `detail-${finding.id}`;

  useEffect(() => {
    setDraft({
      title: finding.title,
      scope: finding.scope,
      provisions: finding.provisions,
      impact: finding.impact,
      articleNumber: finding.articleNumber,
      notes: finding.notes,
    });
  }, [finding]);

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
            <Field label="Discovery">{finding.discoveryTag}</Field>
            <Field label="Verbatim">{finding.verbatimSnippet || "—"}</Field>
            <Field label="Rationale">{finding.mappingRationale || "—"}</Field>
            <Field label="Notes">{finding.notes || "—"}</Field>
            <Field label="Last update">{formatDate(finding.lastUpdate)}</Field>
            <Field label="Source">
              <a href={finding.url} target="_blank" rel="noreferrer noopener">
                {finding.articleNumber} ↗
              </a>
            </Field>
          </dl>

          {editing && (
            <div className="editor">
              <label className="editor__field">
                <span>Title</span>
                <input
                  value={draft.title}
                  onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))}
                />
              </label>
              <label className="editor__field">
                <span>Article / section</span>
                <input
                  value={draft.articleNumber}
                  onChange={(e) => setDraft((prev) => ({ ...prev, articleNumber: e.target.value }))}
                />
              </label>
              <label className="editor__field">
                <span>Scope</span>
                <textarea
                  value={draft.scope}
                  onChange={(e) => setDraft((prev) => ({ ...prev, scope: e.target.value }))}
                />
              </label>
              <label className="editor__field">
                <span>Provisions</span>
                <textarea
                  value={draft.provisions}
                  onChange={(e) => setDraft((prev) => ({ ...prev, provisions: e.target.value }))}
                />
              </label>
              <label className="editor__field">
                <span>Impact</span>
                <textarea
                  value={draft.impact}
                  onChange={(e) => setDraft((prev) => ({ ...prev, impact: e.target.value }))}
                />
              </label>
              <label className="editor__field">
                <span>Notes</span>
                <textarea
                  value={draft.notes}
                  onChange={(e) => setDraft((prev) => ({ ...prev, notes: e.target.value }))}
                />
              </label>
            </div>
          )}

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
            <button
              type="button"
              className="btn btn--edit"
              onClick={() => setEditing((value) => !value)}
            >
              {editing ? "Cancel edit" : "Modify"}
            </button>
            {editing && (
              <button
                type="button"
                className="btn btn--save"
                disabled={saving}
                onClick={async () => {
                  setSaving(true);
                  try {
                    await onModify(finding.id, draft);
                    setEditing(false);
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            )}
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
