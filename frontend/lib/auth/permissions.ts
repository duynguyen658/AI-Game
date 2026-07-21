import type { UserRole } from "./types";

const routeRoles: Array<{ prefix: string; roles: UserRole[] }> = [
  { prefix: "/operations", roles: ["manager", "admin"] },
  { prefix: "/analytics/business-impact", roles: ["manager", "admin"] },
  { prefix: "/prompt-experiments", roles: ["manager", "admin"] },
  { prefix: "/provider-comparisons", roles: ["manager", "admin"] },
  { prefix: "/integrations/n8n", roles: ["manager", "admin"] },
  { prefix: "/prompts", roles: ["reviewer", "manager", "admin"] },
  { prefix: "/approvals", roles: ["reviewer", "manager", "admin"] },
];

export function canAccessPath(role: UserRole, pathname: string) {
  const rule = routeRoles.find(({ prefix }) => pathname === prefix || pathname.startsWith(`${prefix}/`));
  return !rule || rule.roles.includes(role);
}
