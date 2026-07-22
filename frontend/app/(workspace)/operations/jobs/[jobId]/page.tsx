import { JobDetail } from "./view";

export default async function JobDetailPage({ params }: { params: Promise<{ jobId: string }> }) { const { jobId } = await params; return <JobDetail jobId={jobId} />; }
