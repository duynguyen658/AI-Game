"use client";

import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import Link from "next/link";
import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/feedback/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { campaignsApi, type CampaignRecord } from "@/lib/api/campaigns";
import { formatDate } from "@/lib/formatting";

const columns: ColumnDef<CampaignRecord>[] = [
  { id: "campaign", header: "Campaign", accessorFn: (row) => row.campaign.game_name, cell: ({ row }) => <div><Link className="font-semibold text-[var(--accent)] hover:underline" href={`/campaigns/${row.original.campaign.campaign_id}`}>{row.original.campaign.game_name}</Link><p className="mt-0.5 font-mono text-xs text-[var(--muted)]">{row.original.campaign.campaign_id}</p></div> },
  { accessorKey: "status", header: "Status", cell: ({ getValue }) => <StatusBadge status={String(getValue())} /> },
  { id: "market", header: "Market", accessorFn: (row) => row.campaign.market },
  { id: "platforms", header: "Platforms", accessorFn: (row) => row.campaign.platforms.join(", ") },
  { accessorKey: "version", header: "Version" },
  { accessorKey: "updated_at", header: "Updated", cell: ({ getValue }) => formatDate(getValue() as string) },
];

export function CampaignsView() {
  const query = useQuery({ queryKey: ["campaigns"], queryFn: ({ signal }) => campaignsApi.list(signal) });
  return <div className="space-y-6"><PageHeader title="Campaigns" description="Create, run, review, and trace campaign content workflows." actions={<Button asChild><Link href="/campaigns/new"><Plus className="size-4" aria-hidden="true" />New campaign</Link></Button>} />{query.isLoading ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()} /> : query.data?.length ? <DataTable data={query.data} columns={columns} label="Campaigns" /> : <EmptyState title="No campaigns yet" description="Create the first campaign to start a deterministic AI workflow." />}</div>;
}
