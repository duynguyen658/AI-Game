import { DataUpload } from "./upload";
import { PageHeader } from "@/components/layout/page-header";
export const metadata = { title: "New data analysis" };
export default function NewDataAnalysisPage() { return <div className="space-y-6"><PageHeader title="Analyze campaign data" description="CSV is pre-validated in the browser, then validated and processed by the backend." /><DataUpload /></div>; }
