// REST adapter for FindingsRepository. Talks to the FastAPI backend (backend/app/main.py).
// Selected by src/data/index.ts when NEXT_PUBLIC_FINDINGS_API is set; otherwise the mock
// is used. The backend already returns the `Finding` shape, so list() needs no remapping.

import type { Finding, ReviewStatus } from "@/domain/finding";
import type { FindingsRepository } from "./findings.repository";

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected network error";
}

export function createApiRepository(baseUrl: string): FindingsRepository {
  const root = baseUrl.replace(/\/$/, "");
  return {
    async list(): Promise<Finding[]> {
      try {
        const res = await fetch(`${root}/findings`, { cache: "no-store" });
        if (!res.ok) throw new Error(`GET /findings failed: ${res.status}`);
        return (await res.json()) as Finding[];
      } catch (error: unknown) {
        throw new Error(getErrorMessage(error));
      }
    },
    async setReviewStatus(id: string, status: ReviewStatus): Promise<void> {
      try {
        const url = `${root}/findings/${encodeURIComponent(id)}/review?status=${status}`;
        const res = await fetch(url, { method: "PATCH" });
        if (!res.ok) throw new Error(`PATCH review failed: ${res.status}`);
      } catch (error: unknown) {
        throw new Error(getErrorMessage(error));
      }
    },
  };
}
