"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { TooltipProvider } from "@radix-ui/react-tooltip";

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: (count, error) =>
              count < 2 && !(error instanceof Error && error.message === "FORBIDDEN"),
            refetchOnWindowFocus: false,
          },
          mutations: { retry: false },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={250}>{children}</TooltipProvider>
      <Toaster position="top-right" richColors closeButton />
    </QueryClientProvider>
  );
}
