// Container hook: owns review state, delegates persistence to the repository port.
// Components in this feature consume the hook — they never touch the repository directly.

"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  Finding,
  FindingUpdate,
  PipelineRunRequest,
  ReviewStatistics,
  ReviewStatus,
} from "@/domain/finding";
import { getFindingsRepository } from "@/data";
import { applyFilters, type FilterState, type PillarFilter, type StatusFilter } from "./filters";

export interface ReviewState {
  findings: Finding[];
  visible: Finding[];
  filters: FilterState;
  statistics: ReviewStatistics | null;
  busy: boolean;
  setQuery: (q: string) => void;
  setStatus: (s: StatusFilter) => void;
  setPillar: (p: PillarFilter) => void;
  review: (id: string, status: ReviewStatus) => void;
  modify: (id: string, patch: FindingUpdate) => Promise<void>;
  runPipeline: (input: PipelineRunRequest) => Promise<void>;
}

export function useReviewState(initialFindings: Finding[]): ReviewState {
  const [findings, setFindings] = useState<Finding[]>(initialFindings);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [pillar, setPillar] = useState<PillarFilter>("all");
  const [statistics, setStatistics] = useState<ReviewStatistics | null>(null);
  const [busy, setBusy] = useState(false);

  // Refresh from repository on mount so client-only adapters (e.g. REST) get a chance.
  useEffect(() => {
    let cancelled = false;
    const repo = getFindingsRepository();
    Promise.all([repo.list(), repo.getStatistics().catch(() => null)])
      .then(([rows, stats]) => {
        if (cancelled) return;
        if (rows.length) setFindings(rows);
        if (stats) setStatistics(stats);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function refreshStatistics() {
    try {
      setStatistics(await getFindingsRepository().getStatistics());
    } catch {
      // Keep the last known stats when the backend is unavailable.
    }
  }

  function review(id: string, next: ReviewStatus) {
    setFindings((prev) => prev.map((f) => (f.id === id ? { ...f, reviewStatus: next } : f)));
    void getFindingsRepository()
      .setReviewStatus(id, next)
      .then(() => refreshStatistics());
  }

  async function modify(id: string, patch: FindingUpdate) {
    const updated = await getFindingsRepository().update(id, patch);
    setFindings((prev) => prev.map((f) => (f.id === id ? updated : f)));
    await refreshStatistics();
  }

  async function runPipeline(input: PipelineRunRequest) {
    setBusy(true);
    try {
      const rows = await getFindingsRepository().runPipeline(input);
      setFindings(rows);
      await refreshStatistics();
    } finally {
      setBusy(false);
    }
  }

  const filters: FilterState = { query, status, pillar };
  const visible = useMemo(() => applyFilters(findings, filters), [findings, query, status, pillar]);

  return {
    findings,
    visible,
    filters,
    statistics,
    busy,
    setQuery,
    setStatus,
    setPillar,
    review,
    modify,
    runPipeline,
  };
}
