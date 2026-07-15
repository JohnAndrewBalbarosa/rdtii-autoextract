// Adapter selector. The UI imports `getFindingsRepository()` from here; the concrete
// adapter is decided once at module load. Swap mock → REST by changing this file only.

import type { FindingsRepository } from "./findings.repository";
import { createApiRepository } from "./findings.api";
import { createMockRepository } from "./findings.mock";

let instance: FindingsRepository | null = null;

export function getFindingsRepository(): FindingsRepository {
  if (instance) return instance;
  instance =
    process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NODE_ENV === "production"
      ? createApiRepository()
      : createMockRepository();
  return instance;
}

export type { FindingsRepository } from "./findings.repository";
