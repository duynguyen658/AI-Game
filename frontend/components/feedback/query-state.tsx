import { AlertCircle, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError, isApiError } from "@/lib/api/errors";

export function LoadingState({ label = "Loading data" }: { label?: string }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite" aria-busy="true" aria-label={label}>
      <div className="h-10 animate-pulse rounded-md bg-black/6" />
      <div className="h-10 animate-pulse rounded-md bg-black/6" />
      <div className="h-10 animate-pulse rounded-md bg-black/6" />
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-y py-12 text-center">
      <Inbox aria-hidden="true" className="mx-auto size-8 text-[var(--muted)]" />
      <h2 className="mt-3 text-base font-semibold">{title}</h2>
      <p className="mx-auto mt-1 max-w-lg text-sm leading-6 text-[var(--muted)]">{description}</p>
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const apiError = isApiError(error) ? error : new ApiError("The view could not load", 500, "CLIENT_ERROR");
  return (
    <div role="alert" className="border-y border-red-200 bg-[var(--danger-soft)] px-4 py-5 text-[var(--danger)]">
      <div className="flex gap-3"><AlertCircle aria-hidden="true" className="mt-0.5 size-5 shrink-0" /><div><h2 className="font-semibold">{apiError.message}</h2><p className="mt-1 text-xs">Code: {apiError.code}{apiError.correlationId ? ` | Correlation: ${apiError.correlationId}` : ""}</p>{retry ? <Button variant="secondary" size="sm" className="mt-3" onClick={retry}>Try again</Button> : null}</div></div>
    </div>
  );
}
