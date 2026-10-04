import { describe, expect, it } from "vitest";
import { loginDestination, roleHome } from "./roleRoutes";

describe("role safe destinations", () => {
  it.each(["/product/opaque-id", "/product/product%20id", "/", "/account", "/analytics", "/credit-cards", "/support", "/portfolio", "/support-cases", "/support-cases/case-id"])("preserves customer route %s", (path) => {
    expect(loginDestination("customer", path)).toBe(path);
    expect(loginDestination("admin", path)).toBe("/admin/operators");
    expect(loginDestination("operator", path)).toBe("/operator");
  });
  it.each(["//external.test", "https://external.test", "/admin/operators", "/operator", "/account?x=1", "/support-cases/id#x", "/support-cases/..", "/support-cases/%2e%2e", "/support-cases/id\\path", "/unknown", "/product/..", "/product/%2e%2e", "/product/%", "/product/%ff", "/product/id%2fpath", "/product/id%5cpath", "/product/id?x=1"])("rejects unsafe saved path %s", (path) => {
    expect(loginDestination("customer", path)).toBe("/");
  });
  it("rejects the former Spanish product route", () => {
    expect(loginDestination("customer", "/producto/opaque-id")).toBe("/");
  });
  it("uses a role destination without a saved route", () => {
    expect(roleHome("customer")).toBe("/");
    expect(loginDestination("admin")).toBe("/admin/operators");
    expect(loginDestination("operator")).toBe("/operator");
  });
});
