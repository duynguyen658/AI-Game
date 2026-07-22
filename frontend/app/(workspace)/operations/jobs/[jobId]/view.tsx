"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Copy, RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/data-display/status-badge";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { ErrorState, LoadingState } from "@/components/feedback/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { operationsApi } from "@/lib/api/operations";
import { formatDate } from "@/lib/formatting";

export function JobDetail({ jobId }: { jobId: string }) {
  const client = useQueryClient();
  const [action, setAction] = useState<"retry" | "cancel" | null>(null);
  const query = useQuery({ queryKey: ["job", jobId], queryFn: ({ signal }) => operationsApi.job(jobId, signal), refetchInterval: (q) => ["PENDING", "RUNNING"].includes(q.state.data?.status ?? "") ? 3000 : false });
  const mutation = useMutation({ mutationFn: (kind: "retry" | "cancel") => kind === "retry" ? operationsApi.retryJob(jobId) : operationsApi.cancelJob(jobId), onSuccess: () => { toast.success("Job state updated"); setAction(null); client.invalidateQueries({ queryKey: ["job", jobId] }); } });
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const job = query.data;
  const attempts = job.attempts ?? [];
  return <div className="space-y-7"><PageHeader title={job.job_type.replaceAll("_", " ")} description={`Created ${formatDate(job.created_at)} by ${job.created_by}`} actions={<><Button variant="secondary" onClick={() => query.refetch()}><RefreshCw className="size-4" />Refresh</Button>{["FAILED", "DEAD_LETTER", "CANCELLED"].includes(job.status) ? <Button onClick={() => setAction("retry")}><RotateCcw className="size-4" />Retry</Button> : null}{["PENDING", "RUNNING"].includes(job.status) ? <Button variant="danger" onClick={() => setAction("cancel")}><Ban className="size-4" />Cancel</Button> : null}</>} />
    <section className="grid gap-px border bg-[var(--border)] sm:grid-cols-2 lg:grid-cols-4">{[["Status", <StatusBadge key="s" status={job.status} />], ["Attempts", `${job.attempt_count} / ${job.max_attempts}`], ["Priority", job.priority], ["Available", formatDate(job.available_at)], ["Started", formatDate(job.started_at)], ["Completed", formatDate(job.completed_at)], ["Locked by", job.locked_by ?? "Not leased"], ["Lease expires", formatDate(job.lease_expires_at)]].map(([label, value]) => <div className="bg-white p-4" key={String(label)}><dt className="text-xs text-[var(--muted)]">{label}</dt><dd className="mt-1 text-sm font-semibold">{value}</dd></div>)}</section>
    {job.error_code ? <section role="alert" className="border-y border-red-200 bg-[var(--danger-soft)] p-4 text-sm text-[var(--danger)]"><h2 className="font-semibold">{job.error_code}</h2><p className="mt-1">{job.error_message}</p></section> : null}
    <section className="border-y bg-white p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">Traceability</h2><Button variant="ghost" size="sm" onClick={() => navigator.clipboard.writeText(job.correlation_id)}><Copy className="size-4" />Copy correlation ID</Button></div><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2"><div><dt className="text-xs text-[var(--muted)]">Correlation ID</dt><dd className="mt-1 break-all font-mono text-xs">{job.correlation_id}</dd></div><div><dt className="text-xs text-[var(--muted)]">Trace ID</dt><dd className="mt-1 break-all font-mono text-xs">{job.trace_id ?? "Not available"}</dd></div></dl></section>
    <section><h2 className="mb-3 font-semibold">Attempts</h2>{attempts.length ? <div className="overflow-x-auto border-y bg-white"><table className="w-full min-w-[720px] text-left text-sm"><thead><tr className="border-b bg-[var(--surface-subtle)]"><th className="px-4 py-3">Attempt</th><th>Status</th><th>Worker</th><th>Started</th><th>Duration</th><th>Error</th></tr></thead><tbody>{attempts.map((attempt) => <tr className="border-b last:border-0" key={attempt.job_attempt_id}><td className="px-4 py-3">{attempt.attempt_number}</td><td><StatusBadge status={attempt.status} /></td><td className="font-mono text-xs">{attempt.worker_id}</td><td>{formatDate(attempt.started_at)}</td><td>{attempt.duration_ms == null ? "Running" : `${attempt.duration_ms} ms`}</td><td>{attempt.error_code ?? "None"}</td></tr>)}</tbody></table></div> : <p className="border-y py-8 text-center text-sm text-[var(--muted)]">No worker attempts recorded.</p>}</section>
    <ConfirmDialog open={Boolean(action)} onOpenChange={(open) => !open && setAction(null)} title={action === "retry" ? "Retry background job" : "Cancel background job"} description={action === "retry" ? "The backend will create a new attempt only if lifecycle rules allow it." : "Cancellation is audited and may reconcile the related workflow into a terminal state."} confirmLabel={action === "retry" ? "Confirm retry" : "Confirm cancellation"} destructive={action === "cancel"} pending={mutation.isPending} onConfirm={() => action && mutation.mutate(action)} />
  </div>;
}
