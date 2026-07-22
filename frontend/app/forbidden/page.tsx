import { ShieldX } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function ForbiddenPage() {
  return (
    <main className="grid min-h-[100dvh] place-items-center bg-[var(--background)] p-6">
      <div className="max-w-md text-center">
        <ShieldX className="mx-auto size-10 text-[var(--danger)]" aria-hidden="true" />
        <h1 className="mt-4 text-2xl font-semibold">Access is not available</h1>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">Your current role cannot open this workspace.</p>
        <Button asChild className="mt-5"><Link href="/dashboard">Return to dashboard</Link></Button>
      </div>
    </main>
  );
}
