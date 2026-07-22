"use client";

import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import Link from "next/link";
import { DataTable } from "@/components/data-display/data-table";
import { StatusBadge } from "@/components/data-display/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/feedback/query-state";
import { mediaApi, type MediaAsset } from "@/lib/api/media";
import { formatDate } from "@/lib/formatting";
import { compactId } from "@/lib/utils";

const columns = (storyboard: boolean): ColumnDef<MediaAsset>[] => [
  { accessorKey: "media_asset_id", header: "Asset", cell: ({ row }) => <Link className="font-mono text-xs text-[var(--accent)]" href={storyboard ? `/media/storyboards/${row.original.media_asset_id}` : `/media/assets/${row.original.media_asset_id}`}>{compactId(row.original.media_asset_id)}</Link> },
  { accessorKey: "status", header: "Status", cell: ({ getValue }) => <StatusBadge status={String(getValue())} /> },
  { accessorKey: "provider", header: "Provider" },
  { accessorKey: "created_at", header: "Created", cell: ({ getValue }) => formatDate(String(getValue())) },
];

export function MediaHistory() {
  const assets = useQuery({ queryKey: ["media-assets"], queryFn: ({ signal }) => mediaApi.listAssets(signal) });
  const storyboards = useQuery({ queryKey: ["media-storyboards"], queryFn: ({ signal }) => mediaApi.listStoryboards(signal) });
  if (assets.isLoading || storyboards.isLoading) return <LoadingState />;
  if (assets.error || storyboards.error) return <ErrorState error={assets.error ?? storyboards.error!} retry={() => { assets.refetch(); storyboards.refetch(); }} />;
  return <div className="space-y-7"><section><h2 className="mb-3 font-semibold">Image assets</h2>{assets.data?.length ? <DataTable data={assets.data} columns={columns(false)} label="Image assets" /> : <EmptyState title="No image assets" description="Generated image assets will appear here." />}</section><section><h2 className="mb-3 font-semibold">Storyboards</h2>{storyboards.data?.length ? <DataTable data={storyboards.data} columns={columns(true)} label="Storyboards" /> : <EmptyState title="No storyboards" description="Generated storyboards will appear here." />}</section></div>;
}
