// Pure filter logic — no React, no I/O. Trivially unit-testable.

import type { Finding, Pillar, ReviewStatus } from "@/domain/finding";

export type StatusFilter = ReviewStatus | "all";
export type PillarFilter = Pillar | "all";

export interface FilterState {
  query: string;
  status: StatusFilter;
  pillar: PillarFilter;
}

export function applyFilters(findings: Finding[], f: FilterState): Finding[] {
  const q = f.query.trim().toLowerCase();
  return findings.filter((x) => {
    if (f.status !== "all" && x.reviewStatus !== f.status) return false;
    if (f.pillar !== "all" && x.pillar !== f.pillar) return false;
    if (!q) return true;
    return (
      x.title.toLowerCase().includes(q) ||
      x.jurisdiction.toLowerCase().includes(q) ||
      x.provisions.toLowerCase().includes(q) ||
      x.documentTitle.toLowerCase().includes(q)
    );
  });
}
