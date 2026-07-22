import { MessageSquareText } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";

export default function FeedbackPage() { return <div className="space-y-6"><PageHeader title="Feedback" description="Feedback is attached to an eligible completed Applied AI task so backend impact and prompt attribution remain trustworthy." /><section className="border-y bg-white px-5 py-10 text-center"><MessageSquareText className="mx-auto size-8 text-[var(--accent)]" aria-hidden="true" /><h2 className="mt-3 font-semibold">Open a completed task</h2><p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[var(--muted)]">Choose Data analysis, Document processing, Image generation, or Storyboard and open a completed run. Its detail page displays the reusable feedback form when the task is eligible.</p><Button asChild className="mt-5"><Link href="/tasks">Browse AI tasks</Link></Button></section></div>; }
