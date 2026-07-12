"use client";

import type { Finding } from "@/domain/finding";
import { SummaryStats } from "./SummaryStats";
import { FilterBar } from "./FilterBar";
import { FindingRow } from "./FindingRow";
import { useReviewState } from "./use-review-state";

export function ReviewConsole({ initialFindings }: { initialFindings: Finding[] }) {
  const { findings, visible, filters, setQuery, setStatus, setPillar, review } =
    useReviewState(initialFindings);

  return (
    <main className="console">
      <header className="masthead">
        <p className="masthead__kicker">Team Arkova · Zetarix</p>
        <h1 className="masthead__title">Regulatory Findings Review</h1>
        <p className="masthead__lede">
          Article-level findings for <strong>Pillar 6 (Cross-border Data Flows)</strong> and{" "}
          <strong>Pillar 7 (Domestic Data Protection)</strong>. Verify or reject each mapping —
          this human-validation step is the final 20% of the workflow.
        </p>
        <SummaryStats findings={findings} />
      </header>

      <FilterBar
        query={filters.query}
        onQuery={setQuery}
        status={filters.status}
        onStatus={setStatus}
        pillar={filters.pillar}
        onPillar={setPillar}
      />

      <section className="findings" aria-label="Findings">
        {visible.length === 0 ? (
          <p className="empty">No findings match the current filters.</p>
        ) : (
          visible.map((f) => <FindingRow key={f.id} finding={f} onReview={review} />)
        )}
      </section>

      <footer className="console__foot">
        <span>
          Showing {visible.length} of {findings.length} findings
        </span>
        <span className="console__note">Review decisions update the backend training log.</span>
      </footer>
    </main>
  );
}
