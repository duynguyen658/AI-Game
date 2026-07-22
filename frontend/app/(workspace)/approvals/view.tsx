"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/data-display/status-badge";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/feedback/query-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { approvalsApi, type ActionRequest } from "@/lib/api/approvals";
import { formatDate } from "@/lib/formatting";

export function ApprovalCenter() {
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState<{ item: ActionRequest; kind: "approve" | "reject" } | null>(null);
  const [reason, setReason] = useState("");
  const query = useQuery({ queryKey: ["action-requests"], queryFn: ({ signal }) => approvalsApi.actions(signal) });
  const mutation = useMutation({ mutationFn: async () => { if (!decision) throw new Error("No decision selected"); return decision.kind === "approve" ? approvalsApi.approve(decision.item.action_request_id, decision.item.version) : approvalsApi.reject(decision.item.action_request_id, decision.item.version, reason); }, onSuccess: () => { toast.success("Decision recorded"); setDecision(null); setReason(""); queryClient.invalidateQueries({ queryKey: ["action-requests"] }); } });
  return <div className="space-y-6"><PageHeader title="Approval center" description="Review policy-controlled agent actions before execution. Decisions are audited and version checked." />
    {query.isLoading ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => query.refetch()} /> : query.data?.length ? <div className="divide-y border-y bg-white">{query.data.map((item) => <article className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_260px]" key={item.action_request_id}><div><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">{item.action_name}</h2><StatusBadge status={item.status} /><StatusBadge status={item.policy_decision} /></div><p className="mt-2 text-sm leading-6">{item.rationale_summary}</p><dl className="mt-3 grid gap-2 text-xs text-[var(--muted)] sm:grid-cols-2"><div><dt>Agent</dt><dd className="font-medium text-[var(--foreground)]">{item.agent_name}</dd></div><div><dt>Requested</dt><dd className="font-medium text-[var(--foreground)]">{formatDate(item.requested_at)}</dd></div><div><dt>Required role</dt><dd className="font-medium text-[var(--foreground)]">{item.required_role ?? "No manual approval"}</dd></div><div><dt>Campaign</dt><dd className="font-medium text-[var(--foreground)]">{item.campaign_id}</dd></div></dl><details className="mt-3 text-xs"><summary className="cursor-pointer font-medium">Policy and arguments</summary><p className="mt-2 text-[var(--muted)]">{item.policy_reason}</p><pre className="mt-2 overflow-auto bg-[var(--surface-subtle)] p-3">{JSON.stringify(item.arguments, null, 2)}</pre></details></div><div className="border-l-0 pt-1 lg:border-l lg:pl-5"><p className="text-xs font-semibold uppercase text-[var(--muted)]">Human control</p>{item.status === "PENDING_APPROVAL" ? <div className="mt-3 flex flex-wrap gap-2"><Button onClick={() => setDecision({ item, kind: "approve" })}>Approve</Button><Button variant="danger" onClick={() => setDecision({ item, kind: "reject" })}>Reject</Button></div> : <p className="mt-3 text-sm text-[var(--muted)]">This request is no longer awaiting a decision.</p>}</div></article>)}</div> : <EmptyState title="No action requests" description="Policy-controlled agent actions will appear here when review is required." />}
    <ConfirmDialog open={Boolean(decision)} onOpenChange={(open) => !open && setDecision(null)} title={decision?.kind === "approve" ? "Approve controlled action" : "Reject controlled action"} description={decision ? `${decision.item.action_name}: ${decision.item.rationale_summary}` : ""} confirmLabel={decision?.kind === "approve" ? "Confirm approval" : "Confirm rejection"} destructive pending={mutation.isPending} onConfirm={() => mutation.mutate()}>{decision ? <div className="space-y-3"><div className="flex gap-2 border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><ShieldAlert className="size-5 shrink-0" /><p>Verify the target, policy decision, and arguments. Approval permits later execution; it does not bypass backend policy.</p></div>{decision.kind === "reject" ? <div><label htmlFor="rejection-reason" className="mb-1.5 block text-sm font-medium">Rejection reason</label><Textarea id="rejection-reason" value={reason} onChange={(event) => setReason(event.target.value)} required /></div> : null}</div> : null}</ConfirmDialog>
  </div>;
}
