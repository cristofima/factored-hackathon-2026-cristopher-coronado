import { type ReactElement, type ReactNode, isValidElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import { createUiI18n } from "@/i18n";
import OperatorManagement from "./OperatorManagement";
import { Card } from "@/components/ui/card";
import { Table } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { AlertDialog, AlertDialogContent, AlertDialogCancel } from "@/components/ui/alert-dialog";

const harness = vi.hoisted(() => ({
  states: [] as unknown[], cursor: 0,
  pending: { current: null as AbortController | null },
  effects: [] as Array<() => void | (() => void)>,
  query: { isPending: false, isError: false, error: null as unknown, data: [] as unknown[], refetch: vi.fn() },
  invalidate: vi.fn(), create: vi.fn(), change: vi.fn(), logout: vi.fn(),
  locale: "en", creating: false, navigate: vi.fn(), queryOptions: vi.fn(),
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
vi.mock("react-router-dom", () => ({ useNavigate: () => harness.navigate }));
vi.mock("@tanstack/react-query", () => ({ useQuery: (options: unknown) => { harness.queryOptions(options); return harness.query; }, useQueryClient: () => ({ invalidateQueries: harness.invalidate }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { locale: harness.locale }, logout: harness.logout }) }));
vi.mock("@/api/operatorClient", async (original) => ({
  ...await original<typeof import("@/api/operatorClient")>(),
  createOperator: harness.create, changeOperator: harness.change,
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
  return OperatorManagement({ create: harness.creating });
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
function fill(id: string, value: string): void {
  (find((element) => element.props.id === id).props.onChange as (event: { target: { value: string } }) => void)({ target: { value } });
}
async function submit(): Promise<void> {
  await (find((element) => element.type === "form").props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: vi.fn() });
}
const operator = { sub: "operator-id", email: "operator@example.test", locale: "es", role: "operator", identity_version: 1, status: "active", name: "Operator", updated_at: "2026-10-03T15:40:50Z" };

beforeEach(() => {
  vi.clearAllMocks();
  harness.states = [];
  harness.effects = [];
  harness.pending.current = null;
  harness.query = { isPending: false, isError: false, error: null, data: [operator], refetch: vi.fn() };
  harness.locale = "en";
  harness.creating = false;
  harness.navigate.mockImplementation((path: string) => { harness.creating = path === "/admin/operators/create"; harness.states = []; });
  harness.translate = (key) => key;
  harness.create.mockResolvedValue(undefined);
  harness.change.mockResolvedValue(undefined);
  harness.invalidate.mockResolvedValue(undefined);
});

describe("operator identity management form", () => {
  it("uses the shared modal for confirmations and clears passwords on dismissal", () => {
    click("Reset password " + operator.email);
    fill("operator-password", "SyntheticPassword12!");
    expect(find((element) => element.type === AlertDialogContent)).toBeDefined();
    expect(find((element) => element.type === AlertDialogCancel).props.asChild).toBe(true);
    (find((element) => element.type === AlertDialog).props.onOpenChange as (open: boolean) => void)(false);
    expect(elements(render()).some((element) => element.type === AlertDialog)).toBe(false);
    click("Reset password " + operator.email);
    expect(find((element) => element.props.id === "operator-password").props.value).toBe("");
    click("Cancel");
    click("Create operator");
    expect(elements(render()).some((element) => element.type === AlertDialog)).toBe(false);
  });

  it("blocks modal dismissal and duplicate submission while saving, then shows failures inside it", async () => {
    let reject!: (failure: unknown) => void;
    harness.change.mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
    click("Deactivate " + operator.email);
    const work = submit();
    (find((element) => element.type === AlertDialog).props.onOpenChange as (open: boolean) => void)(false);
    const preventDefault = vi.fn();
    (find((element) => element.type === AlertDialogContent).props.onEscapeKeyDown as (event: { preventDefault: () => void }) => void)({ preventDefault });
    expect(preventDefault).toHaveBeenCalledOnce();
    await submit();
    expect(harness.change).toHaveBeenCalledOnce();
    reject(new ApiError("OPERATION_UNAVAILABLE"));
    await work;
    expect(text(find((element) => element.type === AlertDialogContent))).toContain("Operator operation unavailable");
    expect(elements(render()).some((element) => element.type === AlertDialog)).toBe(true);
  });
  it("navigates to a separate creation page without fetching or rendering the list", () => {
    click("Create operator");
    expect(harness.navigate).toHaveBeenCalledWith("/admin/operators/create");
    harness.query.isPending = true;
    expect(elements(render()).some((element) => element.type === "form")).toBe(true);
    expect(elements(render()).some((element) => element.type === Table)).toBe(false);
    expect(text(render())).not.toContain("Loading operators...");
    expect(harness.queryOptions).toHaveBeenLastCalledWith(expect.objectContaining({ enabled: false }));
    harness.query.error = new ApiError("AUTH_REQUIRED");
    harness.effects = [];
    render();
    harness.effects[1]();
    expect(harness.logout).not.toHaveBeenCalled();
    click("Cancel");
    expect(harness.navigate).toHaveBeenLastCalledWith("/admin/operators");
  });
  it("waits for list reconciliation before navigating and suppresses navigation after unmount", async () => {
    let reconcile: () => void = () => undefined;
    harness.invalidate.mockImplementation(() => new Promise<void>((resolve) => { reconcile = resolve; }));
    click("Create operator");
    fill("operator-email", "new@example.test");
    fill("operator-first-name", "New");
    fill("operator-last-name", "Operator");
    fill("operator-password", "test-only-password");
    harness.effects = [];
    render();
    const cleanup = harness.effects[0]();
    const saving = submit();
    await vi.waitFor(() => expect(harness.invalidate).toHaveBeenCalledOnce());
    expect(harness.navigate).not.toHaveBeenCalledWith("/admin/operators");
    expect(find((element) => element.type === "fieldset").props.disabled).toBe(true);
    if (typeof cleanup === "function") cleanup();
    reconcile();
    await saving;
    expect(harness.navigate).not.toHaveBeenCalledWith("/admin/operators");
  });
  it("reuses customer UI cards, tables, status badges and locale selection", () => {
    expect(find((element) => element.type === Card)).toBeDefined();
    expect(find((element) => element.type === Table)).toBeDefined();
    expect(find((element) => element.type === Badge).props.variant).toBe("default");
    harness.query.data = [{ ...operator, status: "inactive" }];
    expect(find((element) => element.type === Badge).props.variant).toBe("secondary");
    click("Create operator");
    expect(find((element) => element.type === Select).props.disabled).toBe(false);
    expect(find((element) => element.props.id === "operator-locale")).toBeDefined();
    expect(elements(render()).some((element) => element.type === "select")).toBe(false);
  });
  it("shows persisted status and only the matching lifecycle action", () => {
    expect(text(render())).toContain("Active");
    expect(elements(render()).some((element) => element.props["aria-label"] === `Activate ${operator.email}`)).toBe(false);
    harness.query.data = [{ ...operator, status: "inactive" }];
    expect(text(render())).toContain("Inactive");
    expect(elements(render()).some((element) => element.props["aria-label"] === `Deactivate ${operator.email}`)).toBe(false);
  });
  it("creates an operator with transient password and refreshes the list", async () => {
    click("Create operator");
    fill("operator-email", "New@example.test");
    fill("operator-first-name", " New ");
    fill("operator-last-name", " Operator ");
    (find((element) => element.type === Select).props.onValueChange as (value: string) => void)("pt");
    fill("operator-password", "test-only-password");
    await submit();
    expect(harness.create).toHaveBeenCalledWith({ email: "new@example.test", first_name: "New", last_name: "Operator", locale: "pt", password: "test-only-password" }, expect.any(AbortSignal));
    expect(harness.invalidate).toHaveBeenCalledWith({ queryKey: ["admin", "operators"] });
    expect(elements(render()).some((element) => element.type === "form")).toBe(false);
    expect(harness.navigate).toHaveBeenLastCalledWith("/admin/operators");
  });
  it.each(["activate", "deactivate", "reset-password"] as const)("confirms %s against the selected identity", async (action) => {
    harness.query.data = [{ ...operator, status: action === "activate" ? "inactive" : "active" }];
    click(`${action === "activate" ? "Activate" : action === "deactivate" ? "Deactivate" : "Reset password"} ${operator.email}`);
    if (action === "reset-password") fill("operator-password", "test-only-password");
    await submit();
    expect(harness.change).toHaveBeenCalledWith(operator.sub, action, expect.any(AbortSignal), action === "reset-password" ? "test-only-password" : undefined);
    expect(harness.invalidate).toHaveBeenCalledOnce();
  });
  it("does not send invalid details and clears the password", async () => {
    click("Create operator");
    fill("operator-email", "invalid");
    fill("operator-password", "short");
    await submit();
    expect(harness.create).not.toHaveBeenCalled();
    expect(find((element) => element.props.id === "operator-password").props.value).toBe("");
    expect(text(render())).toContain("Check the operator details.");
  });
  it("keeps confirmation open until a pending server mutation is reconciled", async () => {
    let complete: () => void = () => undefined;
    harness.change.mockImplementation(() => new Promise<void>((resolve) => { complete = resolve; }));
    click(`Deactivate ${operator.email}`);
    const saving = submit();
    expect(find((element) => element.type === "fieldset").props.disabled).toBe(true);
    expect(find((element) => typeof element.props.onClick === "function" && text(element.props.children as ReactNode) === "Cancel").props.disabled).toBe(true);
    complete();
    await saving;
    expect(harness.invalidate).toHaveBeenCalledOnce();
    expect(text(render())).toContain("Operator updated");
  });
  it("disables shared locale selection while creating an operator and associates password guidance", async () => {
    let complete: () => void = () => undefined;
    harness.create.mockImplementation(() => new Promise<void>((resolve) => { complete = resolve; }));
    click("Create operator");
    fill("operator-email", "new-operator@example.com");
    fill("operator-first-name", "New");
    fill("operator-last-name", "Operator");
    fill("operator-password", "test-only-password");
    expect(find((element) => element.props.id === "operator-password").props["aria-describedby"]).toBe("operator-password-help");
    expect(find((element) => element.props.id === "operator-password-help")).toBeDefined();
    const saving = submit();
    expect(find((element) => element.type === Select).props.disabled).toBe(true);
    expect(find((element) => element.type === "fieldset").props.disabled).toBe(true);
    complete();
    await saving;
    expect(harness.invalidate).toHaveBeenCalledOnce();
  });
  it("cancels an unsent form and clears its password", () => {
    click("Create operator");
    fill("operator-password", "test-only-password");
    click("Cancel");
    click("Create operator");
    expect(find((element) => element.props.id === "operator-password").props.value).toBe("");
    expect(harness.create).not.toHaveBeenCalled();
  });
  it("aborts pending work on unmount and ignores a late successful mutation", async () => {
    let complete: () => void = () => undefined;
    harness.change.mockImplementation(() => new Promise<void>((resolve) => { complete = resolve; }));
    render();
    const cleanup = harness.effects[0]();
    click(`Deactivate ${operator.email}`);
    const saving = submit();
    if (typeof cleanup === "function") cleanup();
    expect((harness.change.mock.calls[0][2] as AbortSignal).aborted).toBe(true);
    complete();
    await saving;
    expect(harness.invalidate).not.toHaveBeenCalled();
    expect(text(render())).not.toContain("Operator updated");
  });
  it("logs out on mutation expiry and shows safe errors for other failures", async () => {
    harness.change.mockRejectedValue(new ApiError("AUTH_REQUIRED"));
    click(`Deactivate ${operator.email}`);
    await submit();
    expect(harness.logout).toHaveBeenCalledOnce();
    harness.change.mockRejectedValue(new Error("private server detail"));
    await submit();
    expect(text(render())).toContain("Operator operation unavailable");
    expect(text(render())).not.toContain("private server detail");
  });
  it("covers list loading, empty, retry and expired-session states", () => {
    harness.query.isPending = true;
    expect(text(render())).toContain("Loading operators...");
    harness.query.isPending = false;
    harness.query.data = [];
    expect(text(render())).toContain("No operators");
    harness.query.isError = true;
    harness.query.error = new ApiError("AUTH_REQUIRED");
    harness.effects = [];
    expect(text(render())).toContain("Session expired");
    harness.effects[1]();
    expect(harness.logout).toHaveBeenCalledOnce();
    click("Retry");
    expect(harness.query.refetch).toHaveBeenCalledOnce();
  });
  it.each(["en", "es", "pt"])("localizes every identity control in %s", (locale) => {
    harness.locale = locale;
    const i18n = createUiI18n(locale);
    const timestamp = find((element) => element.type === "time");
    expect(timestamp.props.dateTime).toBe(operator.updated_at);
    expect(timestamp.props.title).toBe(operator.updated_at);
    expect(text(timestamp)).toBe(new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(operator.updated_at)));
    harness.translate = (key) => {
      expect(i18n.exists(key)).toBe(true);
      return i18n.t(key);
    };
    render();
    click(i18n.t("Create operator"));
    render();
    click(i18n.t("Cancel"));
    click(`${i18n.t("Reset password")} ${operator.email}`);
    render();
    harness.query.isError = true;
    harness.query.error = new ApiError("ACCESS_DENIED");
    render();
  });
});
