export const interactiveRoles = [
  "marketing",
  "reviewer",
  "manager",
  "admin",
] as const;

export type UserRole = (typeof interactiveRoles)[number];

export type SessionUser = {
  actorId: string;
  role: UserRole;
  displayName: string;
};

export const roleLabels: Record<UserRole, string> = {
  marketing: "Marketing",
  reviewer: "Reviewer",
  manager: "Manager",
  admin: "Administrator",
};

export function isUserRole(value: unknown): value is UserRole {
  return interactiveRoles.includes(value as UserRole);
}
