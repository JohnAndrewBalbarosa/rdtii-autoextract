// Domain layer — pure types, no framework, no React, no I/O.
// Mirrors backend core/domain/entities.py (Finding). Kept in sync manually
// until an OpenAPI client is generated from the backend schema.

export type Pillar = 6 | 7;

export type ReviewStatus = "pending" | "verified" | "rejected";

/** An article-level finding mapped to an RDTII indicator (6 mandatory fields + metadata). */
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
  discoveryTag: string;
  verbatimSnippet: string;
  mappingRationale: string;
  locationRef: string | null;
  notes: string;
}

export const PILLAR_LABEL: Record<Pillar, string> = {
  6: "Cross-border Data Flows",
  7: "Domestic Data Protection",
};

export interface FindingUpdate {
  title?: string;
  scope?: string;
  provisions?: string;
  impact?: string;
  reviewStatus?: ReviewStatus;
  articleNumber?: string;
  language?: string;
  indicatorLabel?: string;
  notes?: string;
  verbatimSnippet?: string;
  mappingRationale?: string;
  locationRef?: string | null;
  confidence?: number;
}

export interface PipelineRunRequest {
  country: "SG" | "AU" | "MY";
  pillar: Pillar;
  source: "live" | "gold";
  limit?: number;
}

export interface ReviewStatistics {
  total: number;
  pending: number;
  verified: number;
  rejected: number;
  reviewed: number;
  progress: number;
  by_pillar: Record<string, number>;
  metadata: Record<string, unknown>;
}
