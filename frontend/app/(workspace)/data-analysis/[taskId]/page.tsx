import { DataAnalysisDetail } from "./view";
export const metadata = { title: "Analysis report" };
export default async function DataAnalysisDetailPage({ params }: { params: Promise<{ taskId: string }> }) { const { taskId } = await params; return <DataAnalysisDetail taskId={taskId} />; }
