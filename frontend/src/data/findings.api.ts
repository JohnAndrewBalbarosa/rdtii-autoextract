import type {
  Finding,
  FindingUpdate,
  PipelineRunRequest,
  ReviewStatistics,
  ReviewStatus,
} from "@/domain/finding";
import type { FindingsRepository } from "./findings.repository";

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function createApiRepository(): FindingsRepository {
  return {
    async list() {
      return request<Finding[]>("/findings");
    },
    async setReviewStatus(id: string, status: ReviewStatus) {
      await request<Finding>("/review", {
        method: "POST",
        body: JSON.stringify({ findingId: id, status }),
      });
    },
    async update(id: string, patch: FindingUpdate) {
      return request<Finding>(`/findings/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
    },
    async runPipeline(input: PipelineRunRequest) {
      const result = await request<{ findings: Finding[] }>("/pipeline/run", {
        method: "POST",
        body: JSON.stringify(input),
      });
      return result.findings;
    },
    async getStatistics() {
      return request<ReviewStatistics>("/statistics");
    },
  };
}
