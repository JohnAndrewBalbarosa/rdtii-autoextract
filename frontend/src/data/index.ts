// Adapter selector. The UI imports `getFindingsRepository()` from here; the concrete
// adapter is decided once at module load. Swap mock → REST by changing this file only.

import type { FindingsRepository } from "./findings.repository";
import { createMockRepository } from "./findings.mock";

let instance: FindingsRepository | null = null;

export function getFindingsRepository(): FindingsRepository {
  if (instance) return instance;
  // Future: branch on process.env.NEXT_PUBLIC_FINDINGS_API to use a REST adapter.
  instance = createMockRepository();
  return instance;
}

export type { FindingsRepository } from "./findings.repository";
