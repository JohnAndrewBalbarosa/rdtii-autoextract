// Container hook: owns review state, delegates persistence to the repository port.
// Components in this feature consume the hook — they never touch the repository directly.

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Finding, ReviewStatus } from "@/domain/finding";
import { getFindingsRepository } from "@/data";
import { applyFilters, type FilterState, type PillarFilter, type StatusFilter } from "./filters";

export interface ReviewState {
  findings: Finding[];
  visible: Finding[];
  filters: FilterState;
  setQuery: (q: string) => void;
  setStatus: (s: StatusFilter) => void;
  setPillar: (p: PillarFilter) => void;
  review: (id: string, status: ReviewStatus) => void;
}

export function useReviewState(initialFindings: Finding[]): ReviewState {
  const [findings, setFindings] = useState<Finding[]>(initialFindings);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [pillar, setPillar] = useState<PillarFilter>("all");

  // Refresh from repository on mount so client-only adapters (e.g. REST) get a chance.
  useEffect(() => {
    let cancelled = false;
    getFindingsRepository()
      .list()
      .then((rows) => {
        if (!cancelled && rows.length) setFindings(rows);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const review = useCallback((id: string, next: ReviewStatus) => {
    setFindings((prev) => prev.map((f) => (f.id === id ? { ...f, reviewStatus: next } : f)));
    void getFindingsRepository().setReviewStatus(id, next);
  }, []);

  const filters: FilterState = { query, status, pillar };
  const visible = useMemo(() => applyFilters(findings, filters), [findings, query, status, pillar]);

  return { findings, visible, filters, setQuery, setStatus, setPillar, review };
}
