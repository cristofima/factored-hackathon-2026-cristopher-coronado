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
  const productMatch = requested?.match(/^\/product\/((?:[A-Za-z0-9_.-]|%[A-Fa-f0-9]{2})+)\/?$/);
  if (productMatch) {
    try {
      const id = decodeURIComponent(productMatch[1]);
      const hasControlCharacters = Array.from(id).some((character) => character.charCodeAt(0) < 32);
      if (requested && id !== "." && id !== ".." && !/[\\/?#]/.test(id) && !hasControlCharacters) return requested;
    } catch {
      return roleHome(role);
    }
  }
  return roleHome(role);
}
