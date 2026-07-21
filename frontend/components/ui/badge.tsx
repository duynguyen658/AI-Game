import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded px-2 text-xs font-semibold",
        className,
      )}
      {...props}
    />
  );
}
