"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("route_error", { digest: error.digest });
  }, [error.digest]);
  return (
    <div className="grid min-h-[70dvh] place-items-center p-6 text-center">
      <div><h1 className="text-2xl font-semibold">This view could not load</h1><p className="mt-2 text-sm text-[var(--muted)]">The failure was contained. Try the request again.</p><Button onClick={reset} className="mt-5">Try again</Button></div>
    </div>
  );
}
