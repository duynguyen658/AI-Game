"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, destructive, pending, onConfirm, children }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description: string; confirmLabel: string; destructive?: boolean; pending?: boolean; onConfirm: () => void; children?: ReactNode }) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/45" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-white p-5 shadow-xl"><div className="flex items-start justify-between gap-4"><div><Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title><Dialog.Description className="mt-1 text-sm leading-6 text-[var(--muted)]">{description}</Dialog.Description></div><Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="Close dialog"><X className="size-4" /></Button></Dialog.Close></div>{children ? <div className="mt-4">{children}</div> : null}<div className="mt-5 flex justify-end gap-2"><Dialog.Close asChild><Button variant="secondary">Cancel</Button></Dialog.Close><Button variant={destructive ? "danger" : "primary"} onClick={onConfirm} disabled={pending}>{pending ? "Submitting..." : confirmLabel}</Button></div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
