# RDTII Engine — Frontend

Reviewer-facing UI for the **Global Hackathon on AI for Digital Trade Regulatory Analysis**
(UN ESCAP & KMITL, 2026). Apache 2.0.

Built for **non-technical** users (ESCAP researchers, ministry analysts) — no code, no raw
JSON (R2). Its core surface is the **audit / review view** where the human-validated 20% is
a first-class workflow, not buried (R3, R18): each article-level finding shows the 6
mandatory fields and can be **verified or rejected in seconds** (R6).

> Backend (framework-agnostic core + FastAPI) lives in a **separate repo**: `rdtii-backend`.
> The two communicate over the backend's OpenAPI contract.

## Reference stack (swappable)

- **Next.js (React) + TypeScript** — server components for fast first paint of the audit view.
- Talks to the backend via `NEXT_PUBLIC_API_BASE_URL`.

## Run (dev)

```bash
npm install
npm run dev      # http://localhost:3000
```

Set the API base in `.env.local`:

```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## License

[Apache 2.0](LICENSE).
