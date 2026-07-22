import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-28 w-full resize-y rounded-md border bg-white px-3 py-2 text-sm placeholder:text-[var(--muted)] disabled:bg-[var(--surface-muted)]",
        className,
      )}
      {...props}
    />
  );
}
