# `src/features/review/` — The Review Feature

The human side of the 80/20 split: a fast console where a researcher verifies, rejects, or
edits findings. Container/presentational split — state lives in one hook, the rest is pure
rendering.

## Files

| File | Role |
|---|---|
| `ReviewConsole.tsx` | root client component; composes the feature |
| `use-review-state.ts` | container hook: findings + repository lifecycle + optimistic review |
| `filters.ts` | pure filter logic (no React) |
| `FilterBar.tsx` | search input + status/pillar chips |
| `FindingRow.tsx` | expandable row + accept/reject/edit + source link |
| `SummaryStats.tsx` | counts + review progress (and F1/coverage once wired) |

## State & render flow

```mermaid
flowchart TD
    PAGE["page.tsx (SSR)"] -->|initialFindings| RC[ReviewConsole]
    RC --> HOOK["use-review-state"]
    HOOK -->|list / refetch| REPO["getFindingsRepository()"]
    HOOK -->|applyFilters| FILT["filters.ts (pure)"]
    FILT --> VIS["visible[]"]
    VIS --> ROW["FindingRow × N"]
    RC --> FB[FilterBar] -->|setQuery/status/pillar| HOOK
    RC --> ST[SummaryStats]
    ROW -->|accept/reject| HOOK
    HOOK -->|optimistic update + fire-and-forget| REPO
```

Dependency direction: **UI → Features → Data → Domain** (never reversed). Owned by
**Department 04** ([frontend-reviewer](../../../../docs/departments/04-frontend-reviewer/README.md)).
