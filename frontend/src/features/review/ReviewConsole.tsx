"use client";

import { useState } from "react";
import type { Finding } from "@/domain/finding";
import { SummaryStats } from "./SummaryStats";
import { FilterBar } from "./FilterBar";
import { FindingRow } from "./FindingRow";
import { useReviewState } from "./use-review-state";

export function ReviewConsole({ initialFindings }: { initialFindings: Finding[] }) {
  const { findings, visible, filters, statistics, busy, setQuery, setStatus, setPillar, review, modify, runPipeline } =
    useReviewState(initialFindings);
  const [country, setCountry] = useState<"SG" | "AU" | "MY">("SG");
  const [runPillar, setRunPillar] = useState<6 | 7>(6);
  const [source, setSource] = useState<"live" | "gold">("live");

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
        <form
          className="pipeline-runner"
          onSubmit={(e) => {
            e.preventDefault();
            void runPipeline({ country, pillar: runPillar, source });
          }}
        >
          <label>
            Country
            <select value={country} onChange={(e) => setCountry(e.target.value as "SG" | "AU" | "MY")}>
              <option value="SG">Singapore</option>
              <option value="AU">Australia</option>
              <option value="MY">Malaysia</option>
            </select>
          </label>
          <label>
            Pillar
            <select value={runPillar} onChange={(e) => setRunPillar(Number(e.target.value) as 6 | 7)}>
              <option value={6}>Pillar 6</option>
              <option value={7}>Pillar 7</option>
            </select>
          </label>
          <label>
            Source
            <select value={source} onChange={(e) => setSource(e.target.value as "live" | "gold")}>
              <option value="live">Live crawl</option>
              <option value="gold">Gold baseline</option>
            </select>
          </label>
          <button type="submit" className="btn btn--run" disabled={busy}>
            {busy ? "Running…" : "Run pipeline"}
          </button>
        </form>
        <SummaryStats findings={findings} />
        {typeof statistics?.metadata?.source_used === "string" && (
          <p className="pipeline-note">
            Current dataset source: <strong>{String(statistics.metadata.source_used)}</strong>
          </p>
        )}
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
          visible.map((f) => (
            <FindingRow key={f.id} finding={f} onReview={review} onModify={modify} />
          ))
        )}
      </section>

      <footer className="console__foot">
        <span>
          Showing {visible.length} of {findings.length} findings
        </span>
        <span className="console__note">
          {process.env.NEXT_PUBLIC_API_BASE_URL ? "REST adapter connected." : "Mock fallback active."}
        </span>
      </footer>
    </main>
  );
}
