// Repository port. Concrete adapters (mock, REST, …) implement this.
// The UI never imports an adapter directly — it depends on this port via src/data/index.ts.

import type {
  Finding,
  FindingUpdate,
  PipelineRunRequest,
  ReviewStatistics,
  ReviewStatus,
} from "@/domain/finding";

export interface FindingsRepository {
  list(): Promise<Finding[]>;
  setReviewStatus(id: string, status: ReviewStatus): Promise<void>;
  update(id: string, patch: FindingUpdate): Promise<Finding>;
  runPipeline(input: PipelineRunRequest): Promise<Finding[]>;
  getStatistics(): Promise<ReviewStatistics>;
}
