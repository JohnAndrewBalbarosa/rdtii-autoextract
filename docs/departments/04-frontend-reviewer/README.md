# Department 04 — Frontend / Reviewer UI

**Mission:** The human side of the 80/20 split — a fast, non-technical **review console**
where a policy researcher can verify, reject, or edit any extracted finding in seconds,
with the source always one click away.

**Agent:** `zx-frontend` · **Stack:** Next.js 14 (App Router) + React 18 + TypeScript
strict. **Core rule:** mirror the backend's ports & adapters discipline — UI depends on a
repository *interface*, never a concrete data source.

---

## File structure (what this department owns)

```text
frontend/
├── app/                          # Next.js shell
│   ├── layout.tsx     # root HTML, imports global + review CSS, metadata
│   └── page.tsx       # server component: fetch findings → render ReviewConsole (SSR)
├── src/
│   ├── domain/
│   │   └── finding.ts # Finding type, Pillar, ReviewStatus, PILLAR_LABEL
│   ├── data/                     # Repository pattern (the swap point)
│   │   ├── findings.repository.ts # FindingsRepository interface (port)
│   │   ├── findings.mock.ts       # in-memory mock adapter + seed data
│   │   └── index.ts               # getFindingsRepository(): single swap gateway
│   ├── features/review/          # The review feature (container + presentation)
│   │   ├── ReviewConsole.tsx      # root client component, composes the feature
│   │   ├── use-review-state.ts    # container hook: state + repository lifecycle
│   │   ├── filters.ts             # pure filter logic (no React)
│   │   ├── FilterBar.tsx          # search + status/pillar chips
│   │   ├── FindingRow.tsx         # expandable row + accept/reject/edit
│   │   └── SummaryStats.tsx       # counts + review progress
│   ├── ui/                        # Reusable presentational primitives
│   │   ├── ConfidenceMeter.tsx    # 0–100% bar, high/mid/low level
│   │   ├── PillarTag.tsx          # P6/P7 badge
│   │   └── StatusBadge.tsx        # pending/verified/rejected dot
│   └── styles/
│       ├── globals.css            # resets, typography
│       └── review.css             # console layout (masthead, rows, panels)
├── package.json · tsconfig.json · next.config.mjs · .env.local.example
```

---

## Modularity (functional breakdown)

### Module A — Domain (`src/domain/finding.ts`)
Framework-free types mirroring backend `entities.py`. **`Finding`** holds the 6 mandatory
fields (title, lastUpdate, url, scope, provisions, impact) + mapping metadata (pillar,
indicator, indicatorLabel, confidence, reviewStatus) + audit context (jurisdiction,
documentTitle, articleNumber, language). `Pillar = 6 | 7`,
`ReviewStatus = pending | verified | rejected`.

### Module B — Data layer (`src/data/`) — the swap point
The frontend's own hexagonal seam:
- **`FindingsRepository`** interface: `list()` and `setReviewStatus(id, status)`.
- **`createMockRepository()`** — in-memory adapter seeded with sample findings (SG/VN/TH/
  PH/MY), immutable updates.
- **`getFindingsRepository()`** in `index.ts` — the **single line to change** to swap mock
  for a real REST adapter (`findings.api.ts`) hitting Dept 03's FastAPI. **No UI edits
  needed.** This is the analog of `run.py`'s adapter wiring on the backend.

### Module C — Review feature (`src/features/review/`)
Container/presentational split:
- **`use-review-state`** (container) — owns findings, computes the filtered `visible[]` via
  memoized `applyFilters`, and `review()` does an **optimistic** local update + fire-and-
  forget repository call.
- **`filters.ts`** (pure) — matches on status, pillar, and a case-insensitive query across
  title/jurisdiction/provisions/documentTitle.
- **`ReviewConsole`** composes `SummaryStats` + `FilterBar` + a list of `FindingRow`.
- **`FindingRow`** — one finding: summary line + expandable detail with source link and
  accept/reject/edit; owns only its expand/collapse state.
- **`SummaryStats`** — total / pending / verified / rejected + progress %. (This is where
  F1 / coverage stats render once wired to backend scoring.)

### Module D — UI primitives (`src/ui/`)
Stateless, reusable, no data knowledge: **`ConfidenceMeter`** (color by ≥80/≥65/<65),
**`PillarTag`**, **`StatusBadge`**. These define the review design language.

### Module E — Next.js shell (`app/`)
`layout.tsx` mounts global styles + metadata. `page.tsx` is a **server component** that
fetches initial findings (`getFindingsRepository().list()`) and SSR-renders
`ReviewConsole` (`"use client"`). Clean dependency direction: **UI → Features → Data →
Domain**, never the reverse.

---

## Port seams (the contract)

| Seam | Relationship |
|---|---|
| `FindingsRepository` (TS interface) | The frontend's own port — UI depends on it, not on mock/REST |
| Dept 03 FastAPI `/findings` (future) | A future `findings.api.ts` adapter will consume it; `Finding` (TS) mirrors backend `Finding` (Python) field-for-field |
| `Finding` shape | Must stay in sync with backend `entities.py` + `output_emitter` columns |

> When the backend finding shape changes, `src/domain/finding.ts` is the one file to update
> — every component derives from it.

---

## Verify

```powershell
cd frontend
npm install
npm run dev          # http://localhost:3000 — review console with mock data
npm run build        # production build (Stop-hook verification)
npm run lint
```

---

## Reverse-prompting hooks (task seeds for delegation)

1. **Wire the real API** — *"Add `frontend/src/data/findings.api.ts` implementing
   `FindingsRepository` against Dept 03's `GET /findings` + a status PATCH. Switch
   `getFindingsRepository()` in `index.ts` to use it when `NEXT_PUBLIC_FINDINGS_API` is
   set. Do not touch any component — only the data layer."*
2. **Add F1 / coverage panel** — *"In `SummaryStats.tsx`, render precision/recall/F1 from a
   new `stats` field. Keep it presentational; compute nothing about networking there."*
3. **Audit highlight** — *"In `FindingRow.tsx`, add a 'view source' panel that deep-links
   to the article anchor (Location Reference). Reuse `ui/` primitives; no new global state."*
4. **New filter** — *"Add a jurisdiction filter. Extend `filters.ts` (pure) and `FilterBar`
   only; `applyFilters` must stay a pure function with a unit test."*

**Boundary reminder:** edit only under `frontend/`. The contract with the backend is the
`Finding` shape + the future `/findings` endpoint — coordinate any field change with
Dept 03.
