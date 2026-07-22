import { ProviderComparisonDetail } from "./view";

export default async function ProviderComparisonPage({ params }: { params: Promise<{ comparisonId: string }> }) {
  const { comparisonId } = await params;
  return <ProviderComparisonDetail comparisonId={comparisonId} />;
}
