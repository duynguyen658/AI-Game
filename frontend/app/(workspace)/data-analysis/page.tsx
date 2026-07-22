import { Plus } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { DataAnalysisHistory } from "./view";
export const metadata = { title: "Data analysis" };
export default function DataAnalysisPage() { return <div className="space-y-6"><PageHeader title="Data analysis" description="Validate campaign CSV files and inspect deterministic metrics with AI explanations." actions={<Button asChild><Link href="/data-analysis/new"><Plus className="size-4" />New analysis</Link></Button>} /><DataAnalysisHistory /></div>; }
