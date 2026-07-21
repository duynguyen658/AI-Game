import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "min-h-10 w-full rounded-md border bg-white px-3 text-sm placeholder:text-[var(--muted)] disabled:bg-[var(--surface-muted)] disabled:text-[var(--muted)]",
        className,
      )}
      {...props}
    />
  );
}
