// REST adapter: persists review decisions to the backend training feedback loop (Phase 5).

import type { Finding, ReviewStatus } from "@/domain/finding";
import type { FindingsRepository } from "./findings.repository";

function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

function toReviewPayload(finding: Finding, status: ReviewStatus) {
  return {
    id: finding.id,
    review_status: status,
    jurisdiction: finding.jurisdiction,
    pillar: finding.pillar,
    title: finding.title,
    scope: finding.scope,
    provisions: finding.provisions,
    impact: finding.impact,
    indicator: finding.indicator,
    indicator_label: finding.indicatorLabel,
    document_title: finding.documentTitle,
    article_number: finding.articleNumber,
    language: finding.language,
  };
}

export function createApiRepository(fallback?: FindingsRepository): FindingsRepository {
  const base = apiBase();
  return {
    async list() {
      if (fallback) return fallback.list();
      return [];
    },
    async setReviewStatus(id: string, status: ReviewStatus) {
      if (fallback) await fallback.setReviewStatus(id, status);
      if (status === "pending") return;

      const rows = fallback ? await fallback.list() : [];
      const finding = rows.find((f) => f.id === id);
      if (!finding) return;

      try {
        const res = await fetch(`${base}/training/review-decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(toReviewPayload(finding, status)),
        });
        if (!res.ok) {
          console.warn("[findings.api] review-decision failed:", res.status, await res.text());
          return;
        }
        // Backend debounces rebuild-dataset on review-decision; no separate call needed.
      } catch (err) {
        console.warn("[findings.api] review-decision unreachable:", err);
      }
    },
  };
}
