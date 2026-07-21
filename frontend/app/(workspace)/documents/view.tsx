"use client";

import { useQuery } from "@tanstack/react-query";
import { TaskHistory } from "@/components/data-display/task-history";
import { EmptyState, ErrorState, LoadingState } from "@/components/feedback/query-state";
import { documentsApi } from "@/lib/api/documents";

export function DocumentHistory() {
  const query = useQuery({ queryKey: ["document-tasks"], queryFn: ({ signal }) => documentsApi.list(signal) });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  return query.data?.length
    ? <TaskHistory tasks={query.data} hrefPrefix="/documents" label="Document history" />
    : <EmptyState title="No documents yet" description="Upload a supported document to create the first processing task." />;
}
