import { getSession } from "@/lib/auth/session";
import { DashboardView } from "./view";

export const metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const session = await getSession();
  return <DashboardView role={session!.role} />;
}
