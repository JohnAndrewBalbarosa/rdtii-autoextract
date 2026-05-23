// Frontend contract — mirrors backend core/domain/entities.py (Finding).
// Kept in sync manually until the backend OpenAPI client is generated.

export type Pillar = 6 | 7;

export type ReviewStatus = "pending" | "verified" | "rejected";

/** An article-level finding mapped to an RDTII indicator (the 6 mandatory fields + metadata). */
export interface Finding {
  id: string;
  // --- 6 mandatory fields ---
  title: string;
  lastUpdate: string | null; // ISO date
  url: string;
  scope: string;
  provisions: string;
  impact: string;
  // --- mapping metadata ---
  pillar: Pillar;
  indicator: string; // e.g. "6.2"
  indicatorLabel: string;
  confidence: number; // 0..1
  reviewStatus: ReviewStatus;
  // --- audit context ---
  jurisdiction: string;
  documentTitle: string;
  articleNumber: string; // e.g. "Article 26"
  language: string; // ISO 639-1
}

export const PILLAR_LABEL: Record<Pillar, string> = {
  6: "Cross-border Data Flows",
  7: "Domestic Data Protection",
};
