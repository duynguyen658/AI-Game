"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Play, Square } from "lucide-react";
import { DataTable } from "@/components/data-display/data-table";
import { JobStatusPanel } from "@/components/data-display/job-status-panel";
import { StatusBadge } from "@/components/data-display/status-badge";
import { ErrorState, LoadingState, EmptyState } from "@/components/feedback/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/formatting";
import { providersApi, type ComparisonCase } from "@/lib/api/providers";
import { operationsApi, terminalJobStatuses } from "@/lib/api/operations";

const columns: ColumnDef<ComparisonCase>[] = [
  { accessorKey: "provider", header: "Provider", cell: ({ getValue }) => <span className="capitalize">{String(getValue())}</span> },
  { accessorKey: "model", header: "Model" },
  { accessorKey: "status", header: "Status", cell: ({ getValue }) => <StatusBadge status={String(getValue())} /> },
  { id: "metrics", header: "Metrics", cell: ({ row }) => <span className="font-mono text-xs">{JSON.stringify(row.original.metrics)}</span> },
];

export function ProviderComparisonDetail({ comparisonId }: { comparisonId: string }) {
  const queryClient = useQueryClient();
  const comparison = useQuery({ queryKey: ["provider-comparison", comparisonId], queryFn: ({ signal }) => providersApi.get(comparisonId, signal), refetchInterval: (query) => query.state.data?.status === "RUNNING" ? 2000 : false });
  const job = useQuery({ queryKey: ["job-status", comparison.data?.job_id], queryFn: ({ signal }) => operationsApi.jobStatus(comparison.data!.job_id!, signal), enabled: Boolean(comparison.data?.job_id), refetchInterval: (query) => query.state.data && !terminalJobStatuses.has(query.state.data.status) ? 2000 : false });
  const results = useQuery({ queryKey: ["provider-comparison-results", comparisonId], queryFn: ({ signal }) => providersApi.results(comparisonId, signal), enabled: comparison.data?.status === "COMPLETED" });
  const action = useMutation({ mutationFn: (kind: "run" | "cancel") => kind === "run" ? providersApi.run(comparisonId) : providersApi.cancel(comparisonId), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["provider-comparison", comparisonId] }) });
  if (comparison.isLoading) return <LoadingState />;
  if (comparison.error || !comparison.data) return <ErrorState error={comparison.error} retry={() => comparison.refetch()} />;
  const item = comparison.data;
  return <div className="space-y-7"><PageHeader title="Provider comparison" description={`Created ${formatDate(item.created_at)} by ${item.created_by}`} actions={<>{item.status === "DRAFT" ? <Button onClick={() => action.mutate("run")} disabled={action.isPending}><Play className="size-4" />Run comparison</Button> : null}{item.status === "RUNNING" ? <Button variant="danger" onClick={() => action.mutate("cancel")} disabled={action.isPending}><Square className="size-4" />Cancel</Button> : null}</>} />
    <section className="grid gap-px border bg-[var(--border)] sm:grid-cols-2 lg:grid-cols-4">{[["Status", <StatusBadge key="s" status={item.status} />], ["Providers", item.providers.join(", ")], ["Sample", item.sample_size], ["Dataset", item.dataset_version ?? "Pending"]].map(([label, value]) => <div className="bg-white p-4" key={String(label)}><p className="text-xs text-[var(--muted)]">{label}</p><div className="mt-1 text-sm font-semibold">{value}</div></div>)}</section>
    {job.data ? <JobStatusPanel job={job.data} refreshing={job.isFetching} onRefresh={() => job.refetch()} /> : job.error ? <ErrorState error={job.error} retry={() => job.refetch()} /> : null}
    <section><h2 className="mb-3 font-semibold">Case results</h2>{results.isLoading ? <LoadingState /> : results.error ? <ErrorState error={results.error} /> : results.data?.length ? <DataTable data={results.data} columns={columns} label="Provider result cases" /> : <EmptyState title="No results yet" description="Run the comparison to evaluate provider quality, latency, and cost on the same cases." />}</section>
    {item.report ? <section><h2 className="mb-3 font-semibold">Decision report</h2><pre className="max-h-[420px] overflow-auto border bg-[var(--surface-subtle)] p-4 text-xs leading-6">{JSON.stringify(item.report, null, 2)}</pre></section> : null}
  </div>;
}
