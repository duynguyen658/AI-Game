import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function SessionExpiredPage() {
  return (
    <main className="grid min-h-[100dvh] place-items-center bg-[var(--background)] p-6">
      <div className="max-w-md text-center">
        <h1 className="text-2xl font-semibold">Session expired</h1>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">Sign in again to continue without exposing credentials in the browser.</p>
        <Button asChild className="mt-5"><Link href="/login">Sign in</Link></Button>
      </div>
    </main>
  );
}
