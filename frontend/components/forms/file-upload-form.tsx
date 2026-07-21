"use client";

import { FileUp, ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";

export function FileUploadForm({ accept, label, description, maxBytes = 5_242_880, pending, onSubmit }: { accept: string; label: string; description: string; maxBytes?: number; pending: boolean; onSubmit: (file: File) => void }) {
  const input = useRef<HTMLInputElement>(null); const [file, setFile] = useState<File | null>(null); const [error, setError] = useState<string | null>(null);
  function choose(next: File | null) { setError(null); if (!next) { setFile(null); return; } if (next.size > maxBytes) { setFile(null); setError(`File exceeds ${Math.round(maxBytes / 1_048_576)} MB`); return; } setFile(next); }
  return <form className="max-w-3xl border-y bg-white p-5" onSubmit={(event) => { event.preventDefault(); if (file) onSubmit(file); }}><div className="flex gap-3"><FileUp className="mt-0.5 size-5 text-[var(--accent)]" aria-hidden="true" /><div><h2 className="font-semibold">{label}</h2><p className="mt-1 text-sm leading-6 text-[var(--muted)]">{description}</p></div></div><div className="mt-5 rounded-md border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] p-6 text-center"><input ref={input} type="file" accept={accept} className="sr-only" onChange={(event) => choose(event.target.files?.[0] ?? null)} /><Button type="button" variant="secondary" onClick={() => input.current?.click()}>Choose file</Button><p className="mt-2 text-xs text-[var(--muted)]">{file ? `${file.name} | ${Math.ceil(file.size / 1024)} KB` : `Accepted: ${accept}`}</p></div>{error ? <p role="alert" className="mt-3 text-sm text-[var(--danger)]">{error}</p> : null}<div className="mt-5 flex items-center justify-between gap-4"><p className="flex items-center gap-2 text-xs text-[var(--muted)]"><ShieldCheck className="size-4" aria-hidden="true" />Server validation remains authoritative.</p><Button type="submit" disabled={!file || pending}>{pending ? "Uploading..." : "Upload and run"}</Button></div></form>;
}
