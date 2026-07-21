import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="grid min-h-[70dvh] place-items-center p-6 text-center">
      <div><p className="font-mono text-sm text-[var(--accent)]">404</p><h1 className="mt-2 text-2xl font-semibold">Resource not found</h1><p className="mt-2 text-sm text-[var(--muted)]">The link may be stale or the resource is no longer available.</p><Button asChild className="mt-5"><Link href="/dashboard">Open dashboard</Link></Button></div>
    </div>
  );
}
