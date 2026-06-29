# `src/data/` — Repository Pattern (the swap point)

The frontend's own hexagonal seam. UI depends on the `FindingsRepository` **interface**,
never on a concrete data source. This mirrors the backend's ports & adapters discipline.

## Files

| File | Role |
|---|---|
| `findings.repository.ts` | `FindingsRepository` interface: `list()`, `setReviewStatus(id, status)` |
| `findings.mock.ts` | `createMockRepository()` — in-memory adapter + seed findings |
| `findings.api.ts` | `createApiRepository(baseUrl)` — REST adapter for the FastAPI backend |
| `index.ts` | `getFindingsRepository()` — selects REST when `NEXT_PUBLIC_FINDINGS_API` is set, else mock |

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

> Wiring the real backend is done: `findings.api.ts` exists and `index.ts` flips to it
> when `NEXT_PUBLIC_FINDINGS_API` is set. **No component changes needed.** It calls
> `GET /findings` and `PATCH /findings/{id}/review` on `backend/app/main.py`.
> Owned by **Department 04**
> ([frontend-reviewer](../../../docs/departments/04-frontend-reviewer/README.md)).
