"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BarChart3, FileSearch, ImageIcon, Megaphone, Video } from "lucide-react";
import Link from "next/link";
import { EmptyState, ErrorState, LoadingState } from "@/components/feedback/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { workflowsApi } from "@/lib/api/workflows";

const routes: Record<string, { href: string; icon: typeof Megaphone }> = {
  CAMPAIGN_CONTENT: { href: "/campaigns/new", icon: Megaphone }, DATA_ANALYSIS: { href: "/data-analysis/new", icon: BarChart3 }, DOCUMENT_PROCESSING: { href: "/documents/new", icon: FileSearch }, IMAGE_GENERATION: { href: "/media/images/new", icon: ImageIcon }, VIDEO_STORYBOARD: { href: "/media/storyboards/new", icon: Video },
};

export function TaskCatalog() {
  const query = useQuery({ queryKey: ["applied-workflows"], queryFn: ({ signal }) => workflowsApi.list(signal) });
  return <div className="space-y-6"><PageHeader title="New AI task" description="Choose an authorized workflow. Each task uses a purpose-specific input and asynchronous backend execution." />{query.isLoading ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()} /> : query.data?.length ? <div className="grid gap-px overflow-hidden border bg-[var(--border)] md:grid-cols-2 xl:grid-cols-3">{query.data.map((workflow) => { const route = routes[workflow.workflow_type]; const Icon = route?.icon ?? Megaphone; return <article className="flex min-h-56 flex-col bg-white p-5" key={workflow.workflow_type}><div className="flex items-start justify-between gap-3"><span className="grid size-9 place-items-center rounded-md bg-[var(--accent-soft)] text-[var(--accent)]"><Icon className="size-5" aria-hidden="true" /></span><span className="text-xs font-medium text-[var(--muted)]">{workflow.job_type ? "Asynchronous" : "Synchronous"}</span></div><h2 className="mt-4 font-semibold">{workflow.display_name}</h2><p className="mt-2 flex-1 text-sm leading-6 text-[var(--muted)]">{workflow.description}</p><div className="mt-4 flex items-center justify-between gap-3 border-t pt-4"><p className="text-xs text-[var(--muted)]">{workflow.required_capabilities.length ? workflow.required_capabilities.join(", ") : "Structured input"}</p>{route ? <Button asChild size="sm"><Link href={route.href}>Start <ArrowRight className="size-3.5" /></Link></Button> : null}</div></article>; })}</div> : <EmptyState title="No workflows available" description="The backend registry returned no workflow authorized for this role." />}</div>;
}
