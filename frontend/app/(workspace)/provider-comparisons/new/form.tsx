"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isApiError } from "@/lib/api/errors";
import { providersApi, type ComparisonCreate } from "@/lib/api/providers";

const providerNames = ["mock", "openai", "gemini", "anthropic"] as const;
const schema = z.object({
  prompt_version_id: z.string().uuid(),
  dataset_id: z.string().uuid(),
  providers: z.array(z.enum(providerNames)).min(2).max(3),
  sample_size: z.coerce.number().int().min(1).max(10000),
  mock_model: z.string(), openai_model: z.string(), gemini_model: z.string(), anthropic_model: z.string(),
});
type InputValues = z.input<typeof schema>;
type Values = z.output<typeof schema>;

export function ProviderComparisonForm() {
  const router = useRouter();
  const catalog = useQuery({ queryKey: ["providers"], queryFn: ({ signal }) => providersApi.catalog(signal) });
  const { register, handleSubmit, control, formState: { errors } } = useForm<InputValues, unknown, Values>({
    resolver: zodResolver(schema),
    defaultValues: { prompt_version_id: "", dataset_id: "", providers: ["mock", "openai"], sample_size: 10, mock_model: "mock-deterministic", openai_model: "gpt-4.1-mini", gemini_model: "gemini-2.5-flash", anthropic_model: "claude-sonnet-4-5" },
  });
  const selected = useWatch({ control, name: "providers" }) ?? [];
  const mutation = useMutation({
    mutationFn: (values: Values) => {
      const modelFields = { mock: values.mock_model, openai: values.openai_model, gemini: values.gemini_model, anthropic: values.anthropic_model };
      return providersApi.create({ prompt_version_id: values.prompt_version_id, dataset_id: values.dataset_id, providers: values.providers, model_by_provider: Object.fromEntries(values.providers.map((provider) => [provider, modelFields[provider]])), sample_size: values.sample_size, execution_settings: {} } as ComparisonCreate);
    },
    onSuccess: (value) => router.push(`/provider-comparisons/${value.comparison_id}`),
    onError: (error) => toast.error(isApiError(error) ? error.message : "Unable to create comparison"),
  });
  return <form className="max-w-4xl border-y bg-white p-5" onSubmit={handleSubmit((values) => mutation.mutate(values))}>
    <div className="grid gap-4 sm:grid-cols-2">
      <div><label className="mb-1.5 block text-sm font-medium" htmlFor="provider-prompt">Prompt version ID</label><Input id="provider-prompt" className="font-mono" {...register("prompt_version_id")} />{errors.prompt_version_id ? <p className="mt-1 text-xs text-[var(--danger)]">Enter a valid UUID.</p> : null}</div>
      <div><label className="mb-1.5 block text-sm font-medium" htmlFor="provider-dataset">Evaluation dataset ID</label><Input id="provider-dataset" className="font-mono" {...register("dataset_id")} />{errors.dataset_id ? <p className="mt-1 text-xs text-[var(--danger)]">Enter a valid UUID.</p> : null}</div>
      <fieldset className="sm:col-span-2"><legend className="mb-2 text-sm font-medium">Providers (select 2 or 3)</legend><div className="grid gap-2 sm:grid-cols-2">{providerNames.map((provider) => { const capability = catalog.data?.find((item) => item.provider === provider); return <label className="flex min-h-10 items-center gap-2 border bg-white px-3 text-sm" key={provider}><input type="checkbox" value={provider} disabled={capability?.configured === false} {...register("providers")} /><span className="capitalize">{provider}</span>{capability?.configured === false ? <span className="ml-auto text-xs text-[var(--muted)]">Not configured</span> : null}</label>; })}</div>{errors.providers ? <p className="mt-1 text-xs text-[var(--danger)]">Select two or three providers.</p> : null}</fieldset>
      {selected.map((provider) => <div key={provider}><label className="mb-1.5 block text-sm font-medium capitalize" htmlFor={`${provider}-model`}>{provider} model</label><Input id={`${provider}-model`} {...register(`${provider}_model`)} /></div>)}
      <div><label className="mb-1.5 block text-sm font-medium" htmlFor="provider-sample">Sample size</label><Input id="provider-sample" type="number" min="1" max="10000" {...register("sample_size")} /></div>
    </div><div className="mt-5 flex justify-end"><Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Creating..." : "Create comparison"}</Button></div>
  </form>;
}
