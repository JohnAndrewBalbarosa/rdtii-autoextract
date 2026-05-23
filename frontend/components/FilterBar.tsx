"use client";

import type { Pillar, ReviewStatus } from "@/lib/types";

export type StatusFilter = ReviewStatus | "all";
export type PillarFilter = Pillar | "all";

interface Props {
  query: string;
  onQuery: (q: string) => void;
  status: StatusFilter;
  onStatus: (s: StatusFilter) => void;
  pillar: PillarFilter;
  onPillar: (p: PillarFilter) => void;
}

const STATUSES: StatusFilter[] = ["all", "pending", "verified", "rejected"];

export function FilterBar({ query, onQuery, status, onStatus, pillar, onPillar }: Props) {
  return (
    <div className="filterbar" role="search">
      <input
        className="filterbar__search"
        type="search"
        placeholder="Search title, jurisdiction, provision…"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        aria-label="Search findings"
      />

      <div className="filterbar__group" role="group" aria-label="Filter by status">
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            className={`chip ${status === s ? "chip--active" : ""}`}
            onClick={() => onStatus(s)}
          >
            {s === "all" ? "All" : s[0].toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <div className="filterbar__group" role="group" aria-label="Filter by pillar">
        {(["all", 6, 7] as PillarFilter[]).map((p) => (
          <button
            key={p}
            type="button"
            className={`chip ${pillar === p ? "chip--active" : ""}`}
            onClick={() => onPillar(p)}
          >
            {p === "all" ? "Both pillars" : `Pillar ${p}`}
          </button>
        ))}
      </div>
    </div>
  );
}
