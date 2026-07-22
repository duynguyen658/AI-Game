"use client";

import { useQuery } from "@tanstack/react-query";
import { TaskHistory } from "@/components/data-display/task-history";
import { EmptyState, ErrorState, LoadingState } from "@/components/feedback/query-state";
import { dataAnalysisApi } from "@/lib/api/data-analysis";

export function DataAnalysisHistory() {
  const query = useQuery({ queryKey: ["data-analysis-tasks"], queryFn: ({ signal }) => dataAnalysisApi.list(signal) });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  return query.data?.length
    ? <TaskHistory tasks={query.data} hrefPrefix="/data-analysis" label="Data analysis history" />
    : <EmptyState title="No analyses yet" description="Upload a CSV to create the first analysis task." />;
}
