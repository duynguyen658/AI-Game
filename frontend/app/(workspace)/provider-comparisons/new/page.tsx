import { PageHeader } from "@/components/layout/page-header";
import { ProviderComparisonForm } from "./form";

export default function NewProviderComparisonPage() {
  return <div className="space-y-6"><PageHeader title="New provider comparison" description="Run one approved prompt version and evaluation dataset against two or three configured providers." /><ProviderComparisonForm /></div>;
}
