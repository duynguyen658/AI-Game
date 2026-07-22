"use client";

import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import type { AppliedTask } from "@/lib/api/data-analysis";
import { formatDate } from "@/lib/formatting";
import { compactId } from "@/lib/utils";
import { DataTable } from "./data-table";
import { StatusBadge } from "./status-badge";

export function TaskHistory({ tasks, hrefPrefix, label }: { tasks: AppliedTask[]; hrefPrefix: string; label: string }) {
  const columns: ColumnDef<AppliedTask>[] = [
    { accessorKey: "task_run_id", header: "Task", cell: ({ row }) => <Link className="font-mono text-xs text-[var(--accent)]" href={`${hrefPrefix}/${row.original.task_run_id}`}>{compactId(row.original.task_run_id)}</Link> },
    { accessorKey: "status", header: "Status", cell: ({ getValue }) => <StatusBadge status={String(getValue())} /> },
    { id: "file", header: "File", accessorFn: (row) => String(row.input_metadata.filename ?? "Unknown") },
    { accessorKey: "provider", header: "Provider" },
    { accessorKey: "created_at", header: "Created", cell: ({ getValue }) => formatDate(String(getValue())) },
  ];
  return <DataTable data={tasks} columns={columns} label={label} />;
}
