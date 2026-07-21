import { getSession } from "@/lib/auth/session";
import { redirect } from "next/navigation";
import { CampaignDetailView } from "./view";

export const metadata = { title: "Campaign detail" };
export default async function CampaignDetailPage({ params }: { params: Promise<{ campaignId: string }> }) {
  const [{ campaignId }, session] = await Promise.all([params, getSession()]);
  if (!session) redirect("/login");
  return <CampaignDetailView campaignId={campaignId} role={session.role} />;
}
