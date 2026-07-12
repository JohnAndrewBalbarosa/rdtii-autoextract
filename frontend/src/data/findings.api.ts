// REST adapter: persists review decisions to the backend training feedback loop (Phase 5).

import type { Finding, ReviewStatus } from "@/domain/finding";
import type { FindingsRepository } from "./findings.repository";

function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

function findingsUrl(base: string): string {
  const params = new URLSearchParams({
    country: process.env.NEXT_PUBLIC_RDTII_COUNTRY ?? "SG",
    pillar: process.env.NEXT_PUBLIC_RDTII_PILLAR ?? "6",
    source: process.env.NEXT_PUBLIC_RDTII_SOURCE ?? "gold",
  });
  const limit = process.env.NEXT_PUBLIC_RDTII_LIMIT;
  if (limit) params.set("limit", limit);
  return `${base}/findings?${params.toString()}`;
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
  let cache: Finding[] = [];

  return {
    async list() {
      try {
        const res = await fetch(findingsUrl(base), { cache: "no-store" });
        if (!res.ok) {
          console.warn("[findings.api] findings request failed:", res.status, await res.text());
          cache = fallback ? await fallback.list() : [];
          return cache.map((f) => ({ ...f }));
        }
        const payload = (await res.json()) as { findings?: Finding[] };
        cache = (payload.findings ?? []).map((f) => ({ ...f }));
        return cache.map((f) => ({ ...f }));
      } catch (err) {
        console.warn("[findings.api] findings endpoint unreachable:", err);
        cache = fallback ? await fallback.list() : [];
        return cache.map((f) => ({ ...f }));
      }
    },
    async setReviewStatus(id: string, status: ReviewStatus) {
      if (fallback) await fallback.setReviewStatus(id, status);
      cache = cache.map((f) => (f.id === id ? { ...f, reviewStatus: status } : f));
      if (status === "pending") return;

      const rows = cache.length > 0 ? cache : fallback ? await fallback.list() : [];
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
