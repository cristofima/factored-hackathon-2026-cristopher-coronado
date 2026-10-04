import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createUiI18n } from "@/i18n";
import Dashboard from "@/pages/Dashboard";
import FinancialOverview from "./FinancialOverview";
import ProductSummaryCard from "./ProductSummaryCard";

function expand(node: ReactNode): ReactNode {
  return isValidElement<Parameters<typeof ProductSummaryCard>[0]>(node) && node.type === ProductSummaryCard ? ProductSummaryCard(node.props) : node;
}
import DisputeReportAction from "./DisputeReportAction";

const h = vi.hoisted(() => ({
  cursor: 0, states: [] as unknown[], effects: [] as Array<{ deps: unknown[]; cleanup?: () => void }>,
  pending: [] as Array<() => void>, dirty: false, params: new URLSearchParams(),
  translate: (key: string, _options?: unknown): string => key,
  accounts: vi.fn(), cards: vi.fn(), history: vi.fn(), eligibility: vi.fn(),
  locale: "en", productId: "bank-id", user: "customer-a", session: "session-a",
}));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => {
    const index = h.cursor++;
    if (!(index in h.states)) h.states[index] = typeof initial === "function" ? initial() : initial;
    return [h.states[index], (value: unknown) => {
      const next = typeof value === "function" ? value(h.states[index]) : value;
      if (!Object.is(next, h.states[index])) { h.states[index] = next; h.dirty = true; }
    }];
  },
  useEffect: (effect: () => (() => void) | undefined, deps: unknown[]) => {
    const index = h.cursor++;
    const previous = h.effects[index];
    if (!previous || deps.some((value, i) => !Object.is(value, previous.deps[i]))) {
      h.effects[index] = { deps };
      h.pending.push(() => { previous?.cleanup?.(); h.effects[index].cleanup = effect(); });
    }
  },
}));
vi.mock("react-router-dom", () => ({
  Link: "a",
  useSearchParams: () => [h.params, (params: Record<string, string>) => {
    h.params = new URLSearchParams(params); h.dirty = true;
  }],
}));
vi.mock("react-i18next", async (original) => ({ ...await original<typeof import("react-i18next")>(), useTranslation: () => ({ t: h.translate, i18n: { language: h.locale } }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { id: h.user }, sessionKey: h.session }) }));
vi.mock("@/api/authClient", () => ({ getAccounts: h.accounts, getCards: h.cards }));
vi.mock("@/api/financialClient", () => ({ getTransactions: h.history }));
vi.mock("@/hooks/useDisputeEligibility", () => ({ useDisputeEligibility: h.eligibility }));
vi.mock("./DisputeReportAction", () => ({ default: () => null }));

const account = { product_id: "bank-id", type: "Savings Account", number: "bank-123", currency: "USD", balance: "25", status: "Active", opened: null };
const cards = ["opaque-one", "opaque-two"].map((product_id, i) => ({
  ...account, product_id, type: i ? "Credit Card" : "Debit Card", number: "4111111111111234",
  expires: null, credit_limit: null,
}));
const movement = { id: "tx", product_number: "**** 1234", date: "2026-06-05", amount: "2", currency: "USD", type: "Purchase", status: "Approved", category: "Retail", channel: null, merchant: "Shop" };
type Node = ReactElement<{ children?: ReactNode; [key: string]: unknown }>;
function nodes(node: ReactNode): Node[] {
  node = expand(node);
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!isValidElement<Node["props"]>(node)) return [];
  return [node, ...nodes(node.props.children)];
}
function text(node: ReactNode): string {
  node = expand(node);
  if (Array.isArray(node)) return node.map(text).join(" ");
  if (isValidElement<{ children?: ReactNode }>(node)) return text(node.props.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
function render(catalog = false): ReactNode {
  h.cursor = 0; h.dirty = false;
  const tree = catalog ? Dashboard() : FinancialOverview({ productId: h.productId });
  h.pending.splice(0).forEach((effect) => effect());
  return tree;
}
async function settle(catalog = false): Promise<ReactNode> {
  let tree: ReactNode;
  for (let i = 0; i < 12; i++) { tree = render(catalog); await Promise.resolve(); }
  return tree;
}
function click(node: Node): void { (node.props.onClick as () => void)(); }
function tiles(tree: ReactNode): Node[] { return nodes(tree).filter((node) => node.type === "button" && "aria-pressed" in node.props); }
function actionCount(tree: ReactNode): number { return nodes(tree).filter((node) => node.type === DisputeReportAction).length; }

beforeEach(() => {
  h.effects.forEach((effect) => effect?.cleanup?.());
  h.cursor = 0; h.states = []; h.effects = []; h.pending = []; h.params = new URLSearchParams("start=2026-06-01&end=2026-06-17");
  h.locale = "en"; h.productId = "bank-id"; h.user = "customer-a"; h.session = "session-a"; h.translate = (key) => key;
  h.accounts.mockReset().mockResolvedValue([account]); h.cards.mockReset().mockResolvedValue(cards);
  h.history.mockReset().mockResolvedValue([movement]);
  h.eligibility.mockReset().mockReturnValue({ status: "ready", activeCases: new Map(), refresh: vi.fn() });
});

describe("product financial overview", () => {
  it("keeps the dashboard catalog-only with category filters and opaque links", async () => {
    let tree = await settle(true);
    expect(tiles(tree)).toHaveLength(0);
    const filters = nodes(tree).filter((node) => "aria-pressed" in node.props);
    expect(filters).toHaveLength(3);
    expect(nodes(tree).filter((node) => node.type === "a").map((node) => node.props.to)).toEqual(["/product/bank-id", "/product/opaque-one", "/product/opaque-two"]);
    expect(h.history).not.toHaveBeenCalled();
    expect(text(tree)).not.toContain("4111111111111234");
    click(filters[2]); tree = await settle(true);
    expect(nodes(tree).filter((node) => node.type === "a")).toHaveLength(2);
    expect(text(tree)).not.toContain("Savings Account");
    click(nodes(tree).filter((node) => "aria-pressed" in node.props)[1]); tree = await settle(true);
    expect(nodes(tree).filter((node) => node.type === "a")).toHaveLength(1);
  });

  it("uses only the owned bank number without report actions", async () => {
    const tree = await settle();
    expect(h.history.mock.calls.at(-1)?.slice(0, 3)).toEqual(["bank-123", "2026-06-01", "2026-06-17"]);
    expect(h.history.mock.calls.at(-1)?.[4]).toBeUndefined();
    expect(h.eligibility).toHaveBeenLastCalledWith(false);
    expect(actionCount(tree)).toBe(0);
  });

  it("distinguishes card IDs with the same last four and card-only reporting", async () => {
    h.productId = "opaque-one";
    let tree = await settle();
    expect(h.history.mock.calls.at(-1)?.[4]).toBe("opaque-one");
    expect(h.history.mock.calls.at(-1)?.[0]).toBe("4111 **** **** 1234");
    expect(actionCount(tree)).toBe(1);
    h.productId = "opaque-two"; tree = await settle();
    expect(h.history.mock.calls.at(-1)?.[4]).toBe("opaque-two");
    expect(text(tree)).not.toContain("4111111111111234");
    expect(text(tree)).toContain("**** 1234");
    h.productId = "bank-id"; tree = await settle();
    expect(actionCount(tree)).toBe(0);
  });

  it("paginates complete history without changing complete-window totals", async () => {
    h.history.mockResolvedValue(Array.from({ length: 31 }, (_, i) => ({ ...movement, id: String(i), merchant: "Shop " + i })));
    let tree = await settle();
    expect(nodes(tree).filter((node) => node.type === "tbody").flatMap((node) => nodes(node.props.children).filter((child) => child.type === "tr"))).toHaveLength(25);
    expect(text(tree)).toContain("62.00");
    click(nodes(tree).find((node) => node.props.onClick && text(node.props.children) === "Next")!);
    tree = await settle();
    expect(nodes(tree).filter((node) => node.type === "tbody").flatMap((node) => nodes(node.props.children).filter((child) => child.type === "tr"))).toHaveLength(6);
    expect(h.history).toHaveBeenCalledTimes(1);
  });

  it.each(["missing-number", "duplicate-number", "duplicate-id", "card-account-collision"])("rejects ambiguous or unusable product %s", async (condition) => {
    if (condition === "missing-number") h.accounts.mockResolvedValue([{ ...account, number: null }]);
    if (condition === "duplicate-number") h.accounts.mockResolvedValue([account, { ...account, product_id: "another" }]);
    if (condition === "duplicate-id") h.accounts.mockResolvedValue([account, { ...account, number: "another" }]);
    if (condition === "card-account-collision") h.cards.mockResolvedValue([{ ...cards[0], product_id: account.product_id }]);
    expect(text(await settle())).toContain("Selected product is unavailable.");
    expect(h.history).not.toHaveBeenCalled();
  });

  it.each(["en", "es", "pt"])("localizes product text and statuses in %s", async (locale) => {
    const i18n = createUiI18n(locale); await i18n.changeLanguage(locale);
    h.locale = locale;
    h.translate = (key, options) => String(i18n.t(key, options as never));
    h.productId = "opaque-two";
    const tree = await settle();
    for (const key of ["Product movements", "Filter movements", "Dispute actions", "Credit Card"])
      expect(text(tree)).toContain(String(i18n.t(key)));
    expect(text(tree)).toContain(String(i18n.t("transactions.statuses.Approved", { keySeparator: "." })));
  });

  it.each(["card=foreign-id", "account=foreign-number"])("does not request history for an unowned deep link %s", async (query) => {
    h.productId = query.split("=")[1];
    expect(text(await settle())).toContain("Selected product is unavailable.");
    expect(h.history).not.toHaveBeenCalled(); expect(h.eligibility).toHaveBeenLastCalledWith(false);
  });

  it("retries catalog failure without displaying a partial catalog", async () => {
    h.cards.mockRejectedValueOnce(new Error("private server detail"));
    let tree = await settle();
    expect(text(tree)).toContain("Products are unavailable"); expect(text(tree)).not.toContain("private server detail");
    expect(tiles(tree)).toHaveLength(0); expect(h.history).not.toHaveBeenCalled();
    click(nodes(tree).find((node) => text(node.props.children).includes("Retry") && node.props.onClick) !);
    tree = await settle(); expect(text(tree)).toContain("Filter movements"); expect(h.cards).toHaveBeenCalledTimes(2);
  });

  it("retries card history failure and shows explicit empty results", async () => {
    h.productId = "opaque-one"; h.history.mockRejectedValueOnce(new Error("private detail")).mockResolvedValueOnce([]);
    let tree = await settle(); expect(text(tree)).toContain("Transactions are unavailable"); expect(text(tree)).not.toContain("private detail");
    click(nodes(tree).find((node) => node.props.onClick && text(node.props.children).includes("Retry")) !);
    tree = await settle(); expect(text(tree)).toContain("Empty window"); expect(actionCount(tree)).toBe(0);
  });

  it("shows empty product catalogs and invalid date windows without history", async () => {
    h.accounts.mockResolvedValue([]); h.cards.mockResolvedValue([]);
    expect(text(await settle())).toContain("No products are registered for this customer."); expect(h.history).not.toHaveBeenCalled();
  });

  it("cancels product/date/session requests and ignores their late results", async () => {
    let resolveOld!: (records: typeof movement[]) => void;
    h.history.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    let tree = await settle(); const oldSignal = h.history.mock.calls[0][3] as AbortSignal;
    h.productId = "opaque-one"; tree = await settle(); expect(oldSignal.aborted).toBe(true);
    resolveOld([{ ...movement, merchant: "OLD ACCOUNT ROW" }]); tree = await settle(); expect(text(tree)).not.toContain("OLD ACCOUNT ROW");
    const cardSignal = h.history.mock.calls.at(-1)?.[3] as AbortSignal;
    const date = nodes(tree).find((node) => node.type === "input" && node.props.value === "2026-06-01") !;
    (date.props.onChange as (event: unknown) => void)({ target: { value: "2026-06-03" } });
    tree = await settle(); expect(cardSignal.aborted).toBe(true); expect(h.history.mock.calls.at(-1)?.[1]).toBe("2026-06-03");
    const latest = h.history.mock.calls.at(-1)?.[3] as AbortSignal;
    h.session = "session-b"; h.accounts.mockResolvedValue([]); h.cards.mockResolvedValue([]);
    tree = await settle(); expect(latest.aborted).toBe(true); expect(text(tree)).not.toContain("Shop");
  });

  it("hides stale card rows and reporting immediately on query and identity transitions", async () => {
    h.productId = "opaque-one";
    expect(actionCount(await settle())).toBe(1);
    h.productId = "foreign-id";
    let tree = render();
    expect(text(tree)).not.toContain("Shop"); expect(actionCount(tree)).toBe(0);
    h.productId = "opaque-one"; await settle();
    h.session = "session-b";
    tree = render();
    expect(text(tree)).not.toContain("Shop"); expect(actionCount(tree)).toBe(0);
    expect(tiles(tree)).toHaveLength(0);
  });

  it("rejects reversed dates without fetching history", async () => {
    h.params.set("start", "2026-06-30");
    expect(text(await settle())).toContain("Choose a valid inclusive start and end date.");
    expect(h.history).not.toHaveBeenCalled();
  });
});
