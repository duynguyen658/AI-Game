import { AlertTriangle, CheckCircle2, Circle, Clock3, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const success = new Set(["APPROVED", "COMPLETED", "SUCCEEDED", "RESOLVED", "ACTIVE"]);
const danger = new Set(["FAILED", "REJECTED", "DEAD_LETTER", "CANCELLED"]);
const warning = new Set([
  "PENDING_APPROVAL",
  "READY_FOR_REVIEW",
  "MANUAL_REVIEW_REQUIRED",
  "ACKNOWLEDGED",
  "REVISION_REQUIRED",
]);
const running = new Set(["RUNNING", "PROCESSING", "GENERATING", "TESTING"]);

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  let Icon = Circle;
  let classes = "bg-[var(--surface-muted)] text-[var(--muted)]";
  if (success.has(normalized)) {
    Icon = CheckCircle2;
    classes = "bg-[var(--success-soft)] text-[var(--success)]";
  } else if (danger.has(normalized)) {
    Icon = XCircle;
    classes = "bg-[var(--danger-soft)] text-[var(--danger)]";
  } else if (warning.has(normalized)) {
    Icon = AlertTriangle;
    classes = "bg-[var(--warning-soft)] text-[var(--warning)]";
  } else if (running.has(normalized)) {
    Icon = Clock3;
    classes = "bg-[var(--info-soft)] text-[var(--info)]";
  }
  return (
    <Badge className={classes}>
      <Icon aria-hidden="true" className="size-3.5" strokeWidth={2} />
      <span>{normalized.replaceAll("_", " ")}</span>
    </Badge>
  );
}
