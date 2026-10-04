import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AIAgent from "./AIAgent";

const harness = vi.hoisted(() => ({
  open: false, index: 0, logout: vi.fn(),
  onError: null as null | ((error: { code: string }) => void),
}));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useState: (initial: unknown) => [harness.index++ === 0 ? harness.open : initial, vi.fn()],
  useRef: (current: unknown) => ({ current }),
  useEffect: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ logout: harness.logout }) }));
vi.mock("@/context/AgentResponseContext", () => ({ useAgentResponse: () => ({ triggerOnResponseEnd: vi.fn() }) }));
vi.mock("@/components/chat", () => ({
  ChatProvider: ({ children, onError }: { children: ReactNode; onError: typeof harness.onError }) => {
    harness.onError = onError;
    return children;
  },
  ChatShell: () => "CHAT_COMPOSER",
}));
beforeEach(() => { vi.clearAllMocks(); harness.open = false; harness.index = 0; harness.onError = null; });

describe("customer chat launcher and session rejection", () => {
  it("renders the actual accessible launcher before opening a conversation", () => {
    const html = renderToStaticMarkup(<AIAgent />);
    expect(html).toContain('aria-label="Start Chat"');
    expect(html).toContain("AI Assistant Ready");
    expect(html).not.toContain("CHAT_COMPOSER");
  });
  it.each(["AUTH_REQUIRED", "ACCESS_DENIED"])("tears down the customer session on Responses %s", (code) => {
    harness.open = true;
    expect(renderToStaticMarkup(<AIAgent />)).toContain("CHAT_COMPOSER");
    expect(harness.onError).not.toBeNull();
    harness.onError?.({ code });
    expect(harness.logout).toHaveBeenCalledOnce();
  });
  it.each(["SERVICE_UNAVAILABLE", "RESOURCE_NOT_FOUND"])("preserves the session for %s", (code) => {
    harness.open = true;
    renderToStaticMarkup(<AIAgent />);
    harness.onError?.({ code });
    expect(harness.logout).not.toHaveBeenCalled();
  });
});
