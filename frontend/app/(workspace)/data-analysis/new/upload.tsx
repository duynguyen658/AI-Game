"use client";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { FileUploadForm } from "@/components/forms/file-upload-form";
import { dataAnalysisApi } from "@/lib/api/data-analysis";
import { isApiError } from "@/lib/api/errors";
export function DataUpload() { const router = useRouter(); const mutation = useMutation({ mutationFn: dataAnalysisApi.create, onSuccess: (task) => router.push(`/data-analysis/${task.task_run_id}`), onError: (error) => toast.error(isApiError(error) ? error.message : "Upload failed") }); return <FileUploadForm accept=".csv,text/csv" label="Campaign CSV" description="Up to 5 MB. Metrics are calculated by the backend; the browser does not create authoritative business results." pending={mutation.isPending} onSubmit={(file) => mutation.mutate(file)} />; }
