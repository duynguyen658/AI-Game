import { getSession } from "@/lib/auth/session";
import { redirect } from "next/navigation";
import { DashboardView } from "./view";

export const metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const session = await getSession();
  if (!session) redirect("/login");
  return <DashboardView role={session.role} />;
}
