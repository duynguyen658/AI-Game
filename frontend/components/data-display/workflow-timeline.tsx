import { CheckCircle2, Circle } from "lucide-react";
import type { TimelineEvent } from "@/lib/api/campaigns";
import { formatDate } from "@/lib/formatting";
import { StatusBadge } from "./status-badge";

export function WorkflowTimeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) return <p className="border-y py-8 text-sm text-[var(--muted)]">No workflow events have been recorded yet.</p>;
  return (
    <ol className="relative ml-2 border-l" aria-label="Workflow timeline">
      {events.map((event, index) => <li key={`${event.occurred_at}-${event.event_type}-${index}`} className="relative pb-6 pl-6 last:pb-0"><span className="absolute -left-2 top-0 grid size-4 place-items-center rounded-full bg-white text-[var(--accent)]">{index === events.length - 1 ? <Circle className="size-4 fill-[var(--accent-soft)]" aria-hidden="true" /> : <CheckCircle2 className="size-4" aria-hidden="true" />}</span><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-semibold">{event.summary}</p>{event.status ? <StatusBadge status={event.status} /> : null}</div><div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--muted)]"><time>{formatDate(event.occurred_at)}</time><span>{event.event_type.replaceAll("_", " ")}</span>{event.correlation_id ? <span className="font-mono">Correlation {event.correlation_id.slice(0, 8)}</span> : null}</div></li>)}
    </ol>
  );
}
