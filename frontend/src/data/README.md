# `src/data/` — Repository Pattern (the swap point)

The frontend's own hexagonal seam. UI depends on the `FindingsRepository` **interface**,
never on a concrete data source. This mirrors the backend's ports & adapters discipline.

## Files

| File | Role |
|---|---|
| `findings.repository.ts` | `FindingsRepository` interface: `list()`, `setReviewStatus(id, status)` |
| `findings.mock.ts` | `createMockRepository()` — in-memory adapter + seed findings |
| `index.ts` | `getFindingsRepository()` — the **single line to change** to swap mock → REST |

## Swapping mock for a real API

```mermaid
flowchart TD
    UI["UI + hooks"] -->|depends on| PORT["FindingsRepository<br/>(interface)"]
    GATE["index.ts<br/>getFindingsRepository()"] --> PORT
    GATE -->|default| MOCK["findings.mock.ts<br/>(in-memory)"]
    GATE -.->|when NEXT_PUBLIC_FINDINGS_API set| API["findings.api.ts<br/>(REST → Dept 03 FastAPI)"]
    MOCK ..|> PORT
    API ..|> PORT
```

> Wiring the real backend = add `findings.api.ts` + flip one branch in `index.ts`.
> **No component changes needed.** Owned by **Department 04**
> ([frontend-reviewer](../../../docs/departments/04-frontend-reviewer/README.md)).
