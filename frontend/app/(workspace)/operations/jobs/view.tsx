"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { RefreshCw, Wrench } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/feedback/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { operationsApi, type Job } from "@/lib/api/operations";
import { formatDate } from "@/lib/formatting";
import { compactId } from "@/lib/utils";

const columns: ColumnDef<Job>[] = [
  { accessorKey: "job_type", header: "Type", cell: ({ getValue }) => String(getValue()).replaceAll("_", " ") },
  { accessorKey: "status", header: "Status", cell: ({ getValue }) => <StatusBadge status={String(getValue())} /> },
  { accessorKey: "created_at", header: "Created", cell: ({ getValue }) => formatDate(String(getValue())) },
  { accessorKey: "started_at", header: "Started", cell: ({ getValue }) => formatDate(getValue() as string | null) },
  { id: "attempts", header: "Attempts", accessorFn: (row) => `${row.attempt_count} / ${row.max_attempts}` },
  { accessorKey: "error_code", header: "Safe error", cell: ({ getValue }) => String(getValue() ?? "None") },
  { id: "open", header: "", cell: ({ row }) => <Button asChild variant="ghost" size="sm"><Link href={`/operations/jobs/${row.original.job_id}`}>Inspect <span className="sr-only">job {compactId(row.original.job_id)}</span></Link></Button> },
];

export function JobsConsole() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["jobs"], queryFn: ({ signal }) => operationsApi.jobs(signal), refetchInterval: 10000 });
  const reconcile = useMutation({ mutationFn: operationsApi.reconcileJobs, onSuccess: (result) => { toast.success(`Reclaimed ${result.reclaimed} stale jobs`); client.invalidateQueries({ queryKey: ["jobs"] }); } });
  return <div className="space-y-6"><PageHeader title="Jobs console" description="Inspect queue lifecycle, attempts, safe errors, and worker metadata. Payload editing is intentionally unavailable." actions={<><Button variant="secondary" onClick={() => query.refetch()} disabled={query.isFetching}><RefreshCw className={`size-4 ${query.isFetching ? "animate-spin" : ""}`} />Refresh</Button><Button variant="secondary" onClick={() => reconcile.mutate()} disabled={reconcile.isPending}><Wrench className="size-4" />Reconcile stale</Button></>} />{query.isLoading ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()} /> : query.data?.length ? <DataTable data={query.data} columns={columns} label="Background jobs" /> : <EmptyState title="No jobs" description="Queued Applied AI and maintenance work will appear here." />}</div>;
}
