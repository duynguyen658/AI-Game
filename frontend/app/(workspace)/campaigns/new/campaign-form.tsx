"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { campaignsApi, type CampaignCreate } from "@/lib/api/campaigns";
import { isApiError } from "@/lib/api/errors";

const schema = z.object({
  campaign_id: z.string().trim().min(3).max(100).regex(/^[A-Za-z0-9][A-Za-z0-9_-]*$/, "Use letters, numbers, underscores, or hyphens"),
  game_name: z.string().trim().min(1).max(200), genre: z.string().trim().min(1).max(100),
  target_audience: z.string().trim().min(1).max(300), market: z.string().trim().min(1).max(100),
  platforms: z.array(z.enum(["Facebook", "TikTok", "Discord"])).min(1).max(3),
  campaign_objective: z.string().trim().min(1).max(1000), tone: z.string().trim().min(1).max(500),
  launch_date: z.string().min(1), promotion: z.string().trim().min(1).max(1000), raw_brief: z.string().max(20000).optional(),
});
type Values = z.infer<typeof schema>;
const fields: { name: keyof Pick<Values, "game_name" | "genre" | "target_audience" | "market">; label: string; placeholder: string }[] = [
  { name: "game_name", label: "Game name", placeholder: "Cyber Legends" }, { name: "genre", label: "Genre", placeholder: "Action RPG" },
  { name: "target_audience", label: "Target audience", placeholder: "Players aged 18-30 who follow competitive RPGs" }, { name: "market", label: "Market", placeholder: "Vietnam" },
];
const defaultLaunchDate = new Date(Date.now() + 30 * 86_400_000)
  .toISOString()
  .slice(0, 10);

export function CampaignForm() {
  const router = useRouter(); const client = useQueryClient();
  const { register, handleSubmit, setError, formState: { errors } } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { campaign_id: `CL-${new Date().getFullYear()}-`, game_name: "Cyber Legends", genre: "Action RPG", target_audience: "Players aged 18-30 interested in competitive RPGs", market: "Vietnam", platforms: ["Facebook", "TikTok"], campaign_objective: "Drive qualified pre-registrations for the seasonal launch", tone: "Confident, energetic, and player-first", launch_date: defaultLaunchDate, promotion: "Founder's rewards for early registration", raw_brief: "" } });
  const mutation = useMutation({ mutationFn: (values: Values) => campaignsApi.create({ ...values, raw_brief: values.raw_brief || null } as CampaignCreate), onSuccess: (record) => { client.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Campaign created"); router.push(`/campaigns/${record.campaign.campaign_id}`); }, onError: (error) => { const message = isApiError(error) ? `${error.message}${error.correlationId ? ` (${error.correlationId})` : ""}` : "Unable to create campaign"; setError("root", { message }); } });
  return <form className="max-w-5xl space-y-7" onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate><section className="border-y bg-white px-5 py-5"><h2 className="text-base font-semibold">Identity and audience</h2><div className="mt-4 grid gap-4 md:grid-cols-2"><div><label className="mb-1.5 block text-sm font-medium" htmlFor="campaign_id">Campaign ID</label><Input id="campaign_id" className="font-mono" {...register("campaign_id")} />{errors.campaign_id ? <p className="mt-1 text-xs text-[var(--danger)]">{errors.campaign_id.message}</p> : null}</div>{fields.map((field) => <div key={field.name}><label className="mb-1.5 block text-sm font-medium" htmlFor={field.name}>{field.label}</label><Input id={field.name} placeholder={field.placeholder} {...register(field.name)} />{errors[field.name] ? <p className="mt-1 text-xs text-[var(--danger)]">{errors[field.name]?.message}</p> : null}</div>)}</div><fieldset className="mt-4"><legend className="text-sm font-medium">Platforms</legend><div className="mt-2 flex flex-wrap gap-4">{(["Facebook", "TikTok", "Discord"] as const).map((platform) => <label key={platform} className="flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" value={platform} className="size-4 accent-[var(--accent)]" {...register("platforms")} />{platform}</label>)}</div>{errors.platforms ? <p className="mt-1 text-xs text-[var(--danger)]">Select at least one platform</p> : null}</fieldset></section><section className="border-y bg-white px-5 py-5"><h2 className="text-base font-semibold">Objective and constraints</h2><div className="mt-4 grid gap-4 md:grid-cols-2"><div className="md:col-span-2"><label className="mb-1.5 block text-sm font-medium" htmlFor="campaign_objective">Campaign objective</label><Textarea id="campaign_objective" {...register("campaign_objective")} /></div><div><label className="mb-1.5 block text-sm font-medium" htmlFor="tone">Tone</label><Textarea id="tone" {...register("tone")} /></div><div><label className="mb-1.5 block text-sm font-medium" htmlFor="promotion">Promotion and call to action</label><Textarea id="promotion" {...register("promotion")} /></div><div><label className="mb-1.5 block text-sm font-medium" htmlFor="launch_date">Launch date</label><Input id="launch_date" type="date" {...register("launch_date")} /></div><div className="md:col-span-2"><label className="mb-1.5 block text-sm font-medium" htmlFor="raw_brief">Source context</label><Textarea id="raw_brief" className="min-h-36" placeholder="Optional source context, restrictions, and known facts" {...register("raw_brief")} /></div></div></section>{errors.root ? <p role="alert" className="bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]">{errors.root.message}</p> : null}<div className="flex items-center justify-end gap-3"><Button type="button" variant="secondary" onClick={() => router.back()}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating..." : "Create campaign"}{mutation.isPending ? <Check className="size-4" /> : <ArrowRight className="size-4" />}</Button></div></form>;
}
