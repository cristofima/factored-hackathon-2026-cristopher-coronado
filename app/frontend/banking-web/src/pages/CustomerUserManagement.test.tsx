import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import { createUiI18n } from "@/i18n";
import CustomerUserManagement from "./CustomerUserManagement";
import { Card } from "@/components/ui/card";
import { Table } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { AlertDialog, AlertDialogContent, AlertDialogCancel } from "@/components/ui/alert-dialog";

const harness = vi.hoisted(() => ({
  states: [] as unknown[], cursor: 0,
  pending: { current: null as AbortController | null },
  effects: [] as Array<() => void | (() => void)>,
  query: { isPending: false, isError: false, error: null as unknown, data: [] as unknown[], refetch: vi.fn() },
  invalidate: vi.fn(), change: vi.fn(), logout: vi.fn(),
  locale: "en",
  translate: (key: string) => key,
}));
// Follow rendered form handlers and asynchronous state transitions without a browser.
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = harness.cursor++;
    if (!(index in harness.states)) harness.states[index] = initial;
    return [harness.states[index], (value: unknown) => { harness.states[index] = value; }];
  },
  useRef: () => harness.pending,
  useEffect: (effect: () => void | (() => void)) => { harness.effects.push(effect); },
}));
vi.mock("react-i18next", async (original) => ({
  ...await original<typeof import("react-i18next")>(),
  useTranslation: () => ({ t: (key: string) => harness.translate(key) }),
}));
vi.mock("@tanstack/react-query", () => ({ useQuery: () => harness.query, useQueryClient: () => ({ invalidateQueries: harness.invalidate }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { locale: harness.locale }, logout: harness.logout }) }));
vi.mock("@/api/customerUserClient", async (original) => ({
  ...await original<typeof import("@/api/customerUserClient")>(),
  changeCustomerUser: harness.change,
}));

type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<Record<string, unknown>>(node)) return text(node.props.children as ReactNode);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function render(): Element {
  harness.cursor = 0;
  return CustomerUserManagement();
}
function find(predicate: (element: Element) => boolean): Element {
  const element = elements(render()).find(predicate);
  if (!element) throw new Error("Rendered control not found");
  return element;
}
function click(label: string): void {
  const control = find((element) => typeof element.props.onClick === "function" && (element.props["aria-label"] === label || text(element.props.children as ReactNode) === label));
  (control.props.onClick as () => void)();
}
async function submit(): Promise<void> {
  await (find((element) => element.type === "form").props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: vi.fn() });
}
const customer = { sub: "customer-id", email: "customer@synthetic.invalid", locale: "es", role: "customer", customer_id: "synthetic-customer", identity_version: 1, status: "active", name: "Customer", updated_at: "2026-10-03T15:40:50Z" };

beforeEach(() => {
  vi.clearAllMocks();
  harness.states = [];
  harness.effects = [];
  harness.pending.current = null;
  harness.query = { isPending: false, isError: false, error: null, data: [customer], refetch: vi.fn() };
  harness.locale = "en";
  harness.translate = (key) => key;
  harness.change.mockResolvedValue(undefined);
  harness.invalidate.mockResolvedValue(undefined);
});


describe("customer sign-in management", () => {
  it("uses the shared confirmation modal and supports idle dismissal", () => {
    click("Deactivate " + customer.email);
    expect(find((element) => element.type === AlertDialogContent)).toBeDefined();
    expect(find((element) => element.type === AlertDialogCancel).props.asChild).toBe(true);
    (find((element) => element.type === AlertDialog).props.onOpenChange as (open: boolean) => void)(false);
    expect(elements(render()).some((element) => element.type === AlertDialog)).toBe(false);
    expect(harness.change).not.toHaveBeenCalled();
  });

  it("blocks busy dismissal and duplicate submission, keeping failures inside the modal", async () => {
    let reject!: (failure: unknown) => void;
    harness.change.mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
    click("Deactivate " + customer.email);
    const work = submit();
    (find((element) => element.type === AlertDialog).props.onOpenChange as (open: boolean) => void)(false);
    const preventDefault = vi.fn();
    (find((element) => element.type === AlertDialogContent).props.onEscapeKeyDown as (event: { preventDefault: () => void }) => void)({ preventDefault });
    expect(preventDefault).toHaveBeenCalledOnce();
    await submit();
    expect(harness.change).toHaveBeenCalledOnce();
    reject(new ApiError("OPERATION_UNAVAILABLE"));
    await work;
    expect(text(find((element) => element.type === AlertDialogContent))).toContain("Customer operation unavailable");
    expect(elements(render()).some((element) => element.type === AlertDialog)).toBe(true);
  });
  it("reuses customer UI cards, tables and lifecycle status badges", () => {
    expect(find((element) => element.type === Card)).toBeDefined();
    expect(find((element) => element.type === Table)).toBeDefined();
    expect(find((element) => element.type === Badge).props.variant).toBe("default");
    harness.query.data = [{ ...customer, status: "inactive" }];
    expect(find((element) => element.type === Badge).props.variant).toBe("secondary");
  });
  it.each(["en", "es", "pt"])("uses authenticated %s locale for labels and dates", (locale) => {
    harness.locale = locale;
    const i18n = createUiI18n(locale);
    harness.translate = (key) => String(i18n.t(key));
    expect(text(render())).toContain(i18n.t("Customer users"));
    expect(text(render())).toContain(i18n.t("Customer ID"));
    expect(text(render())).toContain(i18n.t("Active"));
    const date = find((element) => element.type === "time");
    expect(text(date.props.children as ReactNode)).toBe(new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(customer.updated_at)));
    click(String(i18n.t("Deactivate")) + " " + customer.email);
    expect(text(render())).toContain(i18n.t("Confirm customer operation"));
    expect(text(render())).toContain(i18n.t("Changing sign-in access revokes existing sessions. The customer must sign in again after activation."));
  });
  it.each(["activate", "deactivate"] as const)("requires confirmation for %s and refreshes customers", async (action) => {
    harness.query.data = [{ ...customer, status: action === "activate" ? "inactive" : "active" }];
    click((action === "activate" ? "Activate" : "Deactivate") + " " + customer.email);
    expect(harness.change).not.toHaveBeenCalled();
    expect(text(render())).toContain("Changing sign-in access revokes existing sessions.");
    await submit();
    expect(harness.change).toHaveBeenCalledWith(customer.sub, action, expect.any(AbortSignal));
    expect(harness.invalidate).toHaveBeenCalledWith({ queryKey: ["admin", "customers"] });
    expect(text(render())).toContain("Customer user updated");
    expect(elements(render()).some((element) => element.type === "form")).toBe(false);
  });
  it("shows membership, status and persisted date without create/reset controls", () => {
    expect(text(render())).toContain(customer.customer_id);
    expect(text(render())).toContain("Active");
    expect(find((element) => element.type === "time").props.dateTime).toBe(customer.updated_at);
    expect(text(render())).not.toContain("Create customer");
    expect(text(render())).not.toContain("Reset password");
    harness.query.data = [{ ...customer, status: "inactive" }];
    expect(text(render())).toContain("Inactive");
    expect(elements(render()).some((element) => element.props["aria-label"] === "Deactivate " + customer.email)).toBe(false);
  });
  it("cancels before sending", () => {
    click("Deactivate " + customer.email);
    click("Cancel");
    expect(harness.change).not.toHaveBeenCalled();
    expect(elements(render()).some((element) => element.type === "form")).toBe(false);
  });
  it("keeps pending confirmation disabled until refresh", async () => {
    let complete = () => undefined;
    harness.change.mockImplementation(() => new Promise<void>((resolve) => { complete = resolve; }));
    click("Deactivate " + customer.email);
    const saving = submit();
    expect(find((element) => element.type === "fieldset").props.disabled).toBe(true);
    expect(find((element) => typeof element.props.onClick === "function" && text(element.props.children as ReactNode) === "Cancel").props.disabled).toBe(true);
    complete();
    await saving;
    expect(harness.invalidate).toHaveBeenCalledOnce();
  });
  it("aborts on unmount and ignores late completion", async () => {
    let complete = () => undefined;
    harness.change.mockImplementation(() => new Promise<void>((resolve) => { complete = resolve; }));
    render();
    const cleanup = harness.effects[0]();
    click("Deactivate " + customer.email);
    const saving = submit();
    if (typeof cleanup === "function") cleanup();
    expect((harness.change.mock.calls[0][2] as AbortSignal).aborted).toBe(true);
    complete();
    await saving;
    expect(harness.invalidate).not.toHaveBeenCalled();
    expect(text(render())).not.toContain("Customer user updated");
  });
  it.each(["ACCESS_DENIED", "SERVICE_UNAVAILABLE"] as const)("shows controlled %s failure", async (code) => {
    harness.change.mockRejectedValue(new ApiError(code));
    click("Deactivate " + customer.email);
    await submit();
    expect(text(render())).toContain(code === "ACCESS_DENIED" ? "Access denied" : "Customer operation unavailable");
    expect(harness.invalidate).not.toHaveBeenCalled();
  });
  it("logs out on revoked mutation or list session", async () => {
    harness.change.mockRejectedValue(new ApiError("AUTH_REQUIRED"));
    click("Deactivate " + customer.email);
    await submit();
    expect(harness.logout).toHaveBeenCalledOnce();
    harness.logout.mockClear();
    harness.effects = [];
    harness.query.error = new ApiError("AUTH_REQUIRED");
    render();
    harness.effects[1]();
    expect(harness.logout).toHaveBeenCalledOnce();
  });
  it("renders loading, empty and safe retry states", () => {
    harness.query.isPending = true;
    expect(text(render())).toContain("Loading customer users...");
    harness.query.isPending = false;
    harness.query.data = [];
    expect(text(render())).toContain("No customer users");
    harness.query.isError = true;
    harness.query.error = new Error("sensitive upstream details");
    expect(text(render())).toContain("Customer list unavailable");
    expect(text(render())).not.toContain("sensitive upstream details");
    click("Retry");
    expect(harness.query.refetch).toHaveBeenCalledOnce();
  });
});
