import { isValidElement, type ReactElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DisputePreviewConsent } from "./DisputePreviewConsent";
import { ApiError } from "@/api/errors";

const h = vi.hoisted(() => ({ slots: [] as unknown[], cursor: 0, effects: [] as Array<() => void | (() => void)>, create: vi.fn(), recover: vi.fn(), logout: vi.fn(), accepted: vi.fn(), declined: vi.fn(), sessionKey: 1, user: { id: "customer", identityVersion: 1 } as { id: string; identityVersion: number } | null }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(),
  useState: (initial: unknown) => { const i = h.cursor++; if (!(i in h.slots)) h.slots[i] = initial; return [h.slots[i], (v: unknown) => { h.slots[i] = v; }]; },
  useRef: (initial: unknown) => h.slots[h.cursor++] ??= { current: initial },
  useEffect: (effect: () => void | (() => void)) => { h.effects.push(effect); },
}));
vi.mock("react-router-dom", () => ({ Link: "a" }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: h.user, sessionKey: h.sessionKey, logout: h.logout }) }));
vi.mock("@/api/disputeClient", () => ({ openSupportCase: h.create, recoverSupportCase: h.recover }));
const preview = { previewToken: "signed", transactionId: "tx", reason: "Original reason", expiresAt: new Date(Date.now() + 600000).toISOString(), transaction: { id: "tx", country: "CO", city: null } };
const record = { caseId: "case", transactionId: "tx", reason: "Original reason", status: "IN_REVIEW" };
type Element = ReactElement<Record<string, unknown>>;
function elements(node: ReactNode): Element[] { if (Array.isArray(node)) return node.flatMap(elements); if (!isValidElement<Record<string, unknown>>(node)) return []; return [node, ...elements(node.props.children as ReactNode)]; }
function render(value = preview) { h.cursor = 0; return DisputePreviewConsent({ preview: value, onAccepted: h.accepted, onDeclined: h.declined }); }
function find(label: string) { const control = elements(render()).find(e => e.props.children === label); if (!control) throw new Error(`Missing ${label}`); return control; }
function click(label = "Create dispute and request human review") { (find(label).props.onClick as () => void)(); }
async function settle() { for (let i = 0; i < 15; i++) await Promise.resolve(); }
beforeEach(() => { vi.clearAllMocks(); h.slots = []; h.effects = []; h.user = { id: "customer", identityVersion: 1 }; h.sessionKey = 1; h.create.mockResolvedValue(record); h.recover.mockResolvedValue(null); });
describe("pre-case consent", () => {
  it("shows owned context but no receipt before consent and decline never creates", () => { render(); expect(elements(render()).some(e => e.props.children === "View support case")).toBe(false); expect(find("CO")).toBeTruthy(); const decline = find("Decline dispute proposal").props.onClick as () => void; decline(); decline(); expect(h.create).not.toHaveBeenCalled(); expect(h.declined).toHaveBeenCalledOnce(); });
  it("accepts only once and keeps a confirmed receipt despite callback failure", async () => { render(); const action = find("Create dispute and request human review").props.onClick as () => void; h.accepted.mockImplementation(() => { throw new Error("continuation"); }); action(); action(); await settle(); expect(h.create).toHaveBeenCalledOnce(); expect(h.create).toHaveBeenCalledWith("signed", expect.any(AbortSignal)); expect(find("View support case")).toBeTruthy(); expect(h.recover).not.toHaveBeenCalled(); });
  it("recovers a committed lost response without repeating creation", async () => { h.create.mockRejectedValue(new Error("network")); h.recover.mockResolvedValue(record); render(); click(); await settle(); expect(h.create).toHaveBeenCalledOnce(); expect(h.recover).toHaveBeenCalledOnce(); expect(find("View support case")).toBeTruthy(); });
  it.each([
    "DISPUTE_PREVIEW_INVALID", "DISPUTE_PREVIEW_EXPIRED", "DISPUTE_PREVIEW_STALE",
    "DISPUTE_UNAVAILABLE", "DISPUTE_INELIGIBLE", "DISPUTE_CARD_ONLY", "DISPUTE_ALREADY_ACTIVE", "ACCESS_DENIED",
  ] as const)("does not recover or repeat a definitive %s rejection", async code => {
    h.create.mockRejectedValue(new ApiError(code)); render();
    const action = find("Create dispute and request human review").props.onClick as () => void;
    action(); await settle(); action(); await settle();
    expect(h.create).toHaveBeenCalledOnce(); expect(h.recover).not.toHaveBeenCalled();
    expect(h.accepted).not.toHaveBeenCalled();
    const tree = elements(render());
    expect(tree.some(e => e.props.role === "alert")).toBe(true);
    expect(tree.some(e => ["Recover dispute request", "View support case", "Create dispute and request human review"].includes(e.props.children as string))).toBe(false);
  });
  it("accepts an authoritative terminal case recovered after a lost response", async () => {
    h.create.mockRejectedValue(new Error("network")); h.recover.mockResolvedValue({ ...record, status: "RESOLVED" });
    render(); click(); await settle();
    expect(h.create).toHaveBeenCalledOnce(); expect(h.accepted).toHaveBeenCalledWith(expect.objectContaining({ status: "RESOLVED" }));
    expect(find("View support case")).toBeTruthy();
  });
  it("offers recovery only after unknown acceptance and never optimistic resubmission", async () => { h.create.mockRejectedValue(new Error("network")); render(); click(); await settle(); h.recover.mockRejectedValue(new Error("network")); click("Recover dispute request"); await settle(); expect(h.create).toHaveBeenCalledOnce(); expect(h.recover).toHaveBeenCalledTimes(2); expect(find("Recover dispute request")).toBeTruthy(); });
  it("rejects mismatched recovery receipt", async () => { h.create.mockResolvedValue({ ...record, transactionId: "foreign" }); render(); click(); await settle(); expect(h.accepted).not.toHaveBeenCalled(); expect(find("Recover dispute request")).toBeTruthy(); });
  it("expires without creating", async () => { const tree = render({ ...preview, expiresAt: new Date(0).toISOString() }); (elements(tree).find(e => e.props.children === "Create dispute and request human review")!.props.onClick as () => void)(); await settle(); expect(h.create).not.toHaveBeenCalled(); });
  it("invalidates old session synchronously and ignores a late acceptance", async () => { let complete!: (v: unknown) => void; h.create.mockReturnValue(new Promise(resolve => { complete = resolve; })); render(); click(); h.sessionKey++; render(); complete(record); await settle(); expect(h.accepted).not.toHaveBeenCalled(); expect(find("Dispute preview unavailable")).toBeTruthy(); });
  it("aborts on unmount and suppresses late authentication failure", async () => { let reject!: (v: unknown) => void; h.create.mockReturnValue(new Promise((_, no) => { reject = no; })); render(); const cleanup = h.effects[0](); click(); if (cleanup) cleanup(); reject(new ApiError("AUTH_REQUIRED")); await settle(); expect(h.create.mock.calls[0][1].aborted).toBe(true); expect(h.logout).not.toHaveBeenCalled(); });
  it("logs out on active auth failure without recovery", async () => { h.create.mockRejectedValue(new ApiError("AUTH_REQUIRED")); render(); click(); await settle(); expect(h.logout).toHaveBeenCalledOnce(); expect(h.recover).not.toHaveBeenCalled(); });
});
