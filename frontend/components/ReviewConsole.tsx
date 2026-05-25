"use client";

import { useMemo, useState } from "react";
import type { Finding, ReviewStatus } from "@/lib/types";
import { SummaryStats } from "./SummaryStats";
import { FilterBar, type PillarFilter, type StatusFilter } from "./FilterBar";
import { FindingRow } from "./FindingRow";

export function ReviewConsole({ initialFindings }: { initialFindings: Finding[] }) {
  const [findings, setFindings] = useState<Finding[]>(initialFindings);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [pillar, setPillar] = useState<PillarFilter>("all");

  function handleReview(id: string, next: ReviewStatus) {
    // Immutable update — new array, new object (no mutation).
    setFindings((prev) =>
      prev.map((f) => (f.id === id ? { ...f, reviewStatus: next } : f)),
    );
  }

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return findings.filter((f) => {
      if (status !== "all" && f.reviewStatus !== status) return false;
      if (pillar !== "all" && f.pillar !== pillar) return false;
      if (!q) return true;
      return (
        f.title.toLowerCase().includes(q) ||
        f.jurisdiction.toLowerCase().includes(q) ||
        f.provisions.toLowerCase().includes(q) ||
        f.documentTitle.toLowerCase().includes(q)
      );
    });
  }, [findings, query, status, pillar]);

  return (
    <main className="console">
      <header className="masthead">
        <p className="masthead__kicker">UN ESCAP · Zetarix</p>
        <h1 className="masthead__title">Regulatory Findings Review</h1>
        <p className="masthead__lede">
          Article-level findings for <strong>Pillar 6 (Cross-border Data Flows)</strong> and{" "}
          <strong>Pillar 7 (Domestic Data Protection)</strong>. Verify or reject each mapping —
          this human-validation step is the final 20% of the workflow.
        </p>
        <SummaryStats findings={findings} />
      </header>

      <FilterBar
        query={query}
        onQuery={setQuery}
        status={status}
        onStatus={setStatus}
        pillar={pillar}
        onPillar={setPillar}
      />

      <section className="findings" aria-label="Findings">
        {visible.length === 0 ? (
          <p className="empty">No findings match the current filters.</p>
        ) : (
          visible.map((f) => <FindingRow key={f.id} finding={f} onReview={handleReview} />)
        )}
      </section>

      <footer className="console__foot">
        <span>
          Showing {visible.length} of {findings.length} findings
        </span>
        <span className="console__note">Mock data — backend extraction pipeline pending.</span>
      </footer>
    </main>
  );
}
