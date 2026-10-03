import type { UserRole } from "./authClient";

export function roleHome(role: UserRole): string {
  switch (role) {
    case "customer": return "/";
    case "admin": return "/admin/operators";
    case "operator": return "/operator";
  }
}

export function loginDestination(role: UserRole, requested?: string): string {
  if (role !== "customer") return roleHome(role);
  if (requested && /^(\/(credit-cards|portfolio|analytics|account|support)\/?|\/support-cases(?:\/[A-Za-z0-9_-]+)?\/?|\/)$/.test(requested)) {
    return requested;
  }
  return roleHome(role);
}
