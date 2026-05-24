// Route entry. Thin shell — all UI logic lives in src/features/review.
// Server-fetches the initial findings via the repository port so the page is SSR-friendly.

import { ReviewConsole } from "@/features/review/ReviewConsole";
import { getFindingsRepository } from "@/data";

export default async function Home() {
  const initialFindings = await getFindingsRepository().list();
  return <ReviewConsole initialFindings={initialFindings} />;
}
