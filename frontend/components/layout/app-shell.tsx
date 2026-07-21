"use client";

import * as Dialog from "@radix-ui/react-dialog";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Boxes,
  BriefcaseBusiness,
  ChevronRight,
  CircleGauge,
  Database,
  FileSearch,
  FlaskConical,
  HeartPulse,
  ImageIcon,
  LogOut,
  Menu,
  MessagesSquare,
  Network,
  PanelLeftClose,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { roleLabels, type SessionUser, type UserRole } from "@/lib/auth/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type NavItem = {
  href: string;
  label: string;
  icon: typeof CircleGauge;
  roles?: UserRole[];
};

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: CircleGauge },
      { href: "/tasks", label: "New AI task", icon: Sparkles },
      { href: "/campaigns", label: "Campaigns", icon: BriefcaseBusiness },
      { href: "/data-analysis", label: "Data analysis", icon: Database },
      { href: "/documents", label: "Documents", icon: FileSearch },
      { href: "/media", label: "Media studio", icon: ImageIcon },
    ],
  },
  {
    label: "AI operations",
    items: [
      { href: "/prompts", label: "Prompt library", icon: Bot, roles: ["reviewer", "manager", "admin"] },
      { href: "/prompt-experiments", label: "Experiments", icon: FlaskConical, roles: ["manager", "admin"] },
      { href: "/provider-comparisons", label: "Providers", icon: Network, roles: ["manager", "admin"] },
      { href: "/approvals", label: "Approvals", icon: ShieldCheck, roles: ["reviewer", "manager", "admin"] },
    ],
  },
  {
    label: "Business",
    items: [
      { href: "/analytics/business-impact", label: "Business impact", icon: BarChart3, roles: ["manager", "admin"] },
      { href: "/feedback", label: "Feedback", icon: MessagesSquare },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/operations/jobs", label: "Jobs", icon: Boxes, roles: ["manager", "admin"] },
      { href: "/operations/alerts", label: "Alerts", icon: AlertTriangle, roles: ["manager", "admin"] },
      { href: "/operations/health", label: "System health", icon: HeartPulse, roles: ["manager", "admin"] },
      { href: "/integrations/n8n", label: "n8n integrations", icon: Activity, roles: ["manager", "admin"] },
    ],
  },
];

function Navigation({ user, onNavigate }: { user: SessionUser; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary navigation" className="flex-1 overflow-y-auto px-3 py-4">
      {groups.map((group) => {
        const items = group.items.filter((item) => !item.roles || item.roles.includes(user.role));
        if (!items.length) return null;
        return (
          <div className="mb-5" key={group.label}>
            <p className="mb-1 px-2 text-[11px] font-semibold uppercase text-white/45">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    className={cn(
                      "flex min-h-9 items-center gap-3 rounded-md px-2.5 text-sm text-white/72 transition-colors hover:bg-white/8 hover:text-white",
                      active && "bg-[#0e6973] text-white",
                    )}
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0" strokeWidth={1.8} />
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <Link href="/dashboard" className="flex min-h-16 items-center gap-3 border-b border-white/10 px-5 text-white">
      <span className="grid size-8 place-items-center rounded-md bg-[#0f8d99] font-mono text-sm font-bold">CL</span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold">Cyber Legends</span>
        <span className="block truncate text-xs text-white/48">AI Operations</span>
      </span>
    </Link>
  );
}

export function AppShell({ user, children }: { user: SessionUser; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  async function logout() {
    await fetch("/api/session", { method: "DELETE" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="min-h-[100dvh] bg-[var(--background)] lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <a href="#main-content" className="fixed left-3 top-3 z-[100] -translate-y-20 rounded-md bg-white px-3 py-2 text-sm font-semibold shadow-lg focus:translate-y-0">
        Skip to content
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col bg-[var(--surface-strong)] lg:flex">
        <Brand />
        <Navigation user={user} />
        <div className="border-t border-white/10 p-3">
          <div className="mb-2 px-2">
            <p className="truncate text-sm font-medium text-white">{user.displayName}</p>
            <p className="text-xs text-white/48">{roleLabels[user.role]}</p>
          </div>
          <Button onClick={logout} variant="ghost" className="w-full justify-start text-white/72 hover:bg-white/8 hover:text-white">
            <LogOut aria-hidden="true" className="size-4" /> Log out
          </Button>
        </div>
      </aside>

      <div className="min-w-0 lg:col-start-2">
        <header className="sticky top-0 z-20 flex min-h-14 items-center justify-between border-b bg-white/95 px-4 backdrop-blur-sm sm:px-6 lg:px-8">
          <Dialog.Root open={open} onOpenChange={setOpen}>
            <Dialog.Trigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
                <Menu className="size-5" aria-hidden="true" />
              </Button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45" />
              <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-[min(88vw,320px)] flex-col bg-[var(--surface-strong)] shadow-xl">
                <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                <div className="flex items-center justify-between border-b border-white/10 pr-3">
                  <Brand />
                  <Dialog.Close asChild>
                    <Button variant="ghost" size="icon" className="text-white" aria-label="Close navigation">
                      <X className="size-5" aria-hidden="true" />
                    </Button>
                  </Dialog.Close>
                </div>
                <Navigation user={user} onNavigate={() => setOpen(false)} />
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
          <div className="hidden items-center gap-2 text-xs text-[var(--muted)] sm:flex">
            <PanelLeftClose aria-hidden="true" className="size-4" />
            <span>Applied AI workspace</span>
            <ChevronRight aria-hidden="true" className="size-3" />
            <span className="font-medium text-[var(--foreground)]">{roleLabels[user.role]}</span>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm font-medium sm:inline">{user.displayName}</span>
            <span className="size-8 rounded-full border-2 border-[var(--accent)] bg-[var(--accent-soft)]" aria-hidden="true" />
          </div>
        </header>
        <main id="main-content" className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 lg:py-7">
          {children}
        </main>
      </div>
    </div>
  );
}
