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
  },
  {
    id: "au-privacy-app8",
    title: "Cross-border Disclosure of Personal Information",
    lastUpdate: "2024-10-01",
    url: "https://www.legislation.gov.au/C2004A03712",
    scope: "Applies to Australian Privacy Principle entities disclosing personal information overseas.",
    provisions:
      "Before disclosing personal information to an overseas recipient, an entity must take reasonable steps to ensure that the recipient does not breach the Australian Privacy Principles.",
    impact:
      "Creates an accountability-based condition for cross-border disclosure of personal information.",
    pillar: 6,
    indicator: "6.2",
    indicatorLabel: "Conditions on cross-border data transfer",
    confidence: 0.74,
    reviewStatus: "pending",
    jurisdiction: "Australia",
    documentTitle: "Privacy Act 1988",
    articleNumber: "Australian Privacy Principle 8",
    language: "en",
  },
  {
    id: "au-privacy-app11",
    title: "Security of Personal Information",
    lastUpdate: "2024-10-01",
    url: "https://www.legislation.gov.au/C2004A03712",
    scope: "Applies to Australian Privacy Principle entities holding personal information.",
    provisions:
      "An entity must take reasonable steps to protect personal information from misuse, interference, loss, and unauthorised access, modification, or disclosure.",
    impact: "Sets a baseline domestic information-security obligation for regulated entities.",
    pillar: 7,
    indicator: "7.1",
    indicatorLabel: "Security obligations",
    confidence: 0.88,
    reviewStatus: "verified",
    jurisdiction: "Australia",
    documentTitle: "Privacy Act 1988",
    articleNumber: "Australian Privacy Principle 11",
    language: "en",
  },
  {
    id: "sg-pdpa-24",
    title: "Protection of Personal Data",
    lastUpdate: "2021-02-01",
    url: "https://sso.agc.gov.sg/Act/PDPA2012",
    scope: "Applies to organisations holding or controlling personal data in Singapore.",
    provisions:
      "An organisation must make reasonable security arrangements to protect personal data in its possession or under its control.",
    impact: "Codifies a domestic protection duty for organisations handling personal data.",
    pillar: 7,
    indicator: "7.1",
    indicatorLabel: "Security obligations",
    confidence: 0.63,
    reviewStatus: "pending",
    jurisdiction: "Singapore",
    documentTitle: "Personal Data Protection Act 2012",
    articleNumber: "Section 24",
    language: "en",
  },
  {
    id: "my-pdpa-129",
    title: "Transfer of Personal Data Outside Malaysia",
    lastUpdate: "2024-10-17",
    url: "https://mohre.um.edu.my/img/files/Personal%20Data%20Protection%20(PDPA)%20Act%202010.pdf",
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
  };
}
