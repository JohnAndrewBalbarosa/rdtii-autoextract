// Mock adapter for FindingsRepository. Used until the backend pipeline is wired.
// Replace with findings.api.ts (REST) by switching the selector in src/data/index.ts.

import type { Finding, ReviewStatus } from "@/domain/finding";
import type { FindingsRepository } from "./findings.repository";

const SEED: Finding[] = [
  {
    id: "sg-pdpa-26",
    title: "Transfer Limitation Obligation",
    lastUpdate: "2021-02-01",
    url: "https://sso.agc.gov.sg/Act/PDPA2012",
    scope: "Applies to organisations transferring personal data outside Singapore.",
    provisions:
      "An organisation must not transfer personal data outside Singapore except in accordance with prescribed requirements ensuring a comparable standard of protection.",
    impact:
      "Establishes a conditional cross-border transfer regime; enables transfers where the recipient is bound by enforceable obligations.",
    pillar: 6,
    indicator: "6.2",
    indicatorLabel: "Conditions on cross-border data transfer",
    confidence: 0.91,
    reviewStatus: "pending",
    jurisdiction: "Singapore",
    documentTitle: "Personal Data Protection Act 2012",
    articleNumber: "Section 26",
    language: "en",
    discoveryTag: "KNOWN",
    verbatimSnippet:
      "An organisation must not transfer personal data outside Singapore except in accordance with prescribed requirements ensuring a comparable standard of protection.",
    mappingRationale: "This provision directly restricts cross-border transfer conditions.",
    locationRef: "Section 26",
    notes: "",
  },
  {
    id: "vn-decree13-25",
    title: "Cross-border Transfer Impact Assessment",
    lastUpdate: "2023-07-01",
    url: "https://vanban.chinhphu.vn/?pageid=27160&docid=207697",
    scope: "Applies to data processors transferring personal data of Vietnamese citizens abroad.",
    provisions:
      "Prior to transferring personal data abroad, the data processor must prepare a transfer impact assessment dossier and retain it for inspection by the authority.",
    impact:
      "Imposes a documentation and notification burden; a restrictive conditional transfer mechanism.",
    pillar: 6,
    indicator: "6.3",
    indicatorLabel: "Transfer impact / assessment requirement",
    confidence: 0.74,
    reviewStatus: "pending",
    jurisdiction: "Viet Nam",
    documentTitle: "Decree 13/2023/ND-CP on Personal Data Protection",
    articleNumber: "Article 25",
    language: "vi",
    discoveryTag: "NEW",
    verbatimSnippet:
      "Prior to transferring personal data abroad, the data processor must prepare a transfer impact assessment dossier.",
    mappingRationale: "This article imposes an impact-assessment condition on transfer.",
    locationRef: "Article 25",
    notes: "",
  },
  {
    id: "th-pdpa-37",
    title: "Security Measures of Data Controller",
    lastUpdate: "2022-06-01",
    url: "https://www.pdpc.or.th/",
    scope: "Applies to data controllers processing personal data within Thailand.",
    provisions:
      "The data controller shall provide appropriate security measures to prevent unauthorised or unlawful loss, access, use, alteration, or disclosure of personal data.",
    impact: "Sets a baseline domestic data-security standard for controllers.",
    pillar: 7,
    indicator: "7.1",
    indicatorLabel: "Security obligations",
    confidence: 0.88,
    reviewStatus: "verified",
    jurisdiction: "Thailand",
    documentTitle: "Personal Data Protection Act B.E. 2562 (2019)",
    articleNumber: "Section 37",
    language: "th",
    discoveryTag: "KNOWN",
    verbatimSnippet:
      "The data controller shall provide appropriate security measures to prevent unauthorised access.",
    mappingRationale: "This section states an explicit security obligation.",
    locationRef: "Section 37",
    notes: "Translated source.",
  },
  {
    id: "ph-dpa-20",
    title: "Security of Personal Information",
    lastUpdate: "2016-09-09",
    url: "https://www.privacy.gov.ph/data-privacy-act/",
    scope: "Applies to personal information controllers and processors in the Philippines.",
    provisions:
      "The personal information controller must implement reasonable and appropriate organizational, physical, and technical measures intended for the protection of personal information.",
    impact: "Codifies an accountability-based domestic protection duty.",
    pillar: 7,
    indicator: "7.2",
    indicatorLabel: "Accountability of controller",
    confidence: 0.63,
    reviewStatus: "pending",
    jurisdiction: "Philippines",
    documentTitle: "Data Privacy Act of 2012 (RA 10173)",
    articleNumber: "Section 20",
    language: "en",
    discoveryTag: "KNOWN",
    verbatimSnippet:
      "The personal information controller must implement reasonable and appropriate measures intended for protection.",
    mappingRationale: "This provision imposes controller accountability duties.",
    locationRef: "Section 20",
    notes: "",
  },
  {
    id: "my-pdpa-129",
    title: "Transfer of Personal Data Outside Malaysia",
    lastUpdate: "2024-10-17",
    url: "https://www.pdp.gov.my/",
    scope: "Applies to data users transferring personal data to a place outside Malaysia.",
    provisions:
      "A data user shall not transfer personal data to a place outside Malaysia unless to a place specified by the Minister, or where prescribed safeguards apply.",
    impact: "Adequacy-list-based cross-border regime with ministerial discretion.",
    pillar: 6,
    indicator: "6.1",
    indicatorLabel: "Restriction on cross-border transfer",
    confidence: 0.52,
    reviewStatus: "rejected",
    jurisdiction: "Malaysia",
    documentTitle: "Personal Data Protection Act 2010",
    articleNumber: "Section 129",
    language: "en",
    discoveryTag: "KNOWN",
    verbatimSnippet:
      "A data user shall not transfer personal data to a place outside Malaysia unless safeguards apply.",
    mappingRationale: "This section directly restricts outbound transfer.",
    locationRef: "Section 129",
    notes: "",
  },
];

export function createMockRepository(): FindingsRepository {
  const store: Finding[] = SEED.map((f) => ({ ...f }));
  return {
    async list() {
      return store.map((f) => ({ ...f }));
    },
    async setReviewStatus(id: string, status: ReviewStatus) {
      const i = store.findIndex((f) => f.id === id);
      if (i >= 0) store[i] = { ...store[i], reviewStatus: status };
    },
    async update(id, patch) {
      const i = store.findIndex((f) => f.id === id);
      if (i >= 0) {
        store[i] = { ...store[i], ...patch };
        return { ...store[i] };
      }
      throw new Error(`Finding not found: ${id}`);
    },
    async runPipeline() {
      return store.map((f) => ({ ...f }));
    },
    async getStatistics() {
      const pending = store.filter((f) => f.reviewStatus === "pending").length;
      const verified = store.filter((f) => f.reviewStatus === "verified").length;
      const rejected = store.filter((f) => f.reviewStatus === "rejected").length;
      const reviewed = verified + rejected;
      return {
        total: store.length,
        pending,
        verified,
        rejected,
        reviewed,
        progress: store.length ? Math.round((reviewed / store.length) * 100) : 0,
        by_pillar: {
          "6": store.filter((f) => f.pillar === 6).length,
          "7": store.filter((f) => f.pillar === 7).length,
        },
        metadata: { source_used: "mock" },
      };
    },
  };
}
