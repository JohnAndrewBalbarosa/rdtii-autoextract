import { ReviewConsole } from "@/components/ReviewConsole";
import { MOCK_FINDINGS } from "@/lib/mock-data";

export default function Home() {
  // Server-rendered shell; findings are mock until the backend pipeline is wired.
  return <ReviewConsole initialFindings={MOCK_FINDINGS} />;
}
