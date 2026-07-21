import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex min-h-9 items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]",
        secondary:
          "border bg-white text-[var(--foreground)] hover:bg-[var(--surface-muted)]",
        ghost: "text-[var(--foreground)] hover:bg-black/5",
        danger: "bg-[var(--danger)] text-white hover:bg-[#982f36]",
      },
      size: {
        sm: "min-h-8 px-2.5 text-xs",
        md: "min-h-9 px-3",
        lg: "min-h-11 px-4",
        icon: "size-9 p-0",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({
  className,
  variant,
  size,
  asChild,
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
