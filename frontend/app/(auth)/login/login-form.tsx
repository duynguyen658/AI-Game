"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { interactiveRoles, roleLabels } from "@/lib/auth/types";

const schema = z.object({
  displayName: z.string().trim().min(2, "Enter at least 2 characters").max(100),
  actorId: z.string().trim().min(2).max(100),
  role: z.enum(interactiveRoles),
});
type Values = z.infer<typeof schema>;

export function LoginForm() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { displayName: "Maya Tran", actorId: "demo-marketing", role: "marketing" },
  });

  async function submit(values: Values) {
    setServerError(null);
    const response = await fetch("/api/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(values),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { message?: string } | null;
      setServerError(body?.message ?? "Unable to start the demo session");
      return;
    }
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <form onSubmit={handleSubmit(submit)} className="mt-8 space-y-4" noValidate>
      <div className="rounded-md border border-amber-200/25 bg-amber-100/8 p-3 text-xs leading-5 text-amber-50/80">
        <div className="flex gap-2">
          <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <p>Demo authentication uses development headers behind an HttpOnly session. It is not production SSO.</p>
        </div>
      </div>
      {serverError ? <p role="alert" className="rounded-md bg-red-400/12 p-3 text-sm text-red-100">{serverError}</p> : null}
      <div>
        <label htmlFor="displayName" className="mb-1.5 block text-sm font-medium">Display name</label>
        <Input id="displayName" autoComplete="name" className="border-white/20 bg-white/9 text-white placeholder:text-white/35" {...register("displayName")} />
        {errors.displayName ? <p className="mt-1 text-xs text-red-200">{errors.displayName.message}</p> : null}
      </div>
      <div>
        <label htmlFor="actorId" className="mb-1.5 block text-sm font-medium">Demo actor ID</label>
        <Input id="actorId" autoComplete="username" className="border-white/20 bg-white/9 font-mono text-white placeholder:text-white/35" {...register("actorId")} />
      </div>
      <div>
        <label htmlFor="role" className="mb-1.5 block text-sm font-medium">Role</label>
        <select id="role" className="min-h-10 w-full rounded-md border border-white/20 bg-[#172329] px-3 text-sm text-white" {...register("role")}>
          {interactiveRoles.map((role) => <option value={role} key={role}>{roleLabels[role]}</option>)}
        </select>
      </div>
      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Starting session..." : "Enter workspace"}
        <ArrowRight aria-hidden="true" className="size-4" />
      </Button>
    </form>
  );
}
