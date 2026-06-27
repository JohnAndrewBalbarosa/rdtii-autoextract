// Adapter selector. The UI imports `getFindingsRepository()` from here; the concrete
// adapter is decided once at module load. Swap mock → REST by changing this file only.

import type { FindingsRepository } from "./findings.repository";
import { createMockRepository } from "./findings.mock";
import { createApiRepository } from "./findings.api";

let instance: FindingsRepository | null = null;

export function getFindingsRepository(): FindingsRepository {
  if (instance) return instance;
  // Use the REST backend when configured; fall back to the in-memory mock otherwise.
  const apiBase = process.env.NEXT_PUBLIC_FINDINGS_API;
  instance = apiBase ? createApiRepository(apiBase) : createMockRepository();
  return instance;
}

export type { FindingsRepository } from "./findings.repository";
