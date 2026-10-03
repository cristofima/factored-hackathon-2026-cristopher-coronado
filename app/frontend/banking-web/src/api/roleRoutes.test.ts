import { describe, expect, it } from "vitest";
import { loginDestination, roleHome } from "./roleRoutes";

describe("role safe destinations", () => {
  it.each(["/", "/account", "/analytics", "/credit-cards", "/support", "/portfolio", "/support-cases", "/support-cases/case-id"])("preserves customer route %s", (path) => {
    expect(loginDestination("customer", path)).toBe(path);
    expect(loginDestination("admin", path)).toBe("/admin/operators");
    expect(loginDestination("operator", path)).toBe("/operator");
  });
  it.each(["//external.test", "https://external.test", "/admin/operators", "/operator", "/account?x=1", "/support-cases/id#x", "/support-cases/..", "/support-cases/%2e%2e", "/support-cases/id\\path", "/unknown"])("rejects unsafe saved path %s", (path) => {
    expect(loginDestination("customer", path)).toBe("/");
  });
  it("uses a role destination without a saved route", () => {
    expect(roleHome("customer")).toBe("/");
    expect(loginDestination("admin")).toBe("/admin/operators");
    expect(loginDestination("operator")).toBe("/operator");
  });
});
