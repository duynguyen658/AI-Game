import { CampaignForm } from "./campaign-form";
import { PageHeader } from "@/components/layout/page-header";

export const metadata = { title: "New campaign" };
export default function NewCampaignPage() { return <div className="space-y-6"><PageHeader title="New campaign" description="Define the campaign brief used by the deterministic workflow and specialist agents." /><CampaignForm /></div>; }
