import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { UiLocaleProvider } from "./UiLocaleProvider";
import Sidebar from "../components/Sidebar";
import Login from "../pages/Login";

const auth = vi.hoisted(() => ({ user: null as { locale: string } | null }));
vi.mock("./AuthContext", () => ({
  useAuth: () => ({ ...auth, loading: false, login: vi.fn(), logout: vi.fn() }),
}));

describe("authenticated UI localization", () => {
  const renderWorkspace = () =>
    renderToStaticMarkup(
      <MemoryRouter>
        <UiLocaleProvider>
          <Sidebar />
        </UiLocaleProvider>
      </MemoryRouter>,
    );

  it("renders profile languages, user switches and logout without retained locale", () => {
    auth.user = { locale: "es" };
    expect(renderWorkspace()).toContain("Resumen");
    expect(renderWorkspace()).not.toContain('href="/portfolio"');
    expect(renderWorkspace()).not.toContain('href="/credit-cards"');
    auth.user = { locale: "pt" };
    expect(renderWorkspace()).toContain("Resumo");
    expect(renderWorkspace()).not.toContain("Resumen");
    auth.user = { locale: "fr" };
    expect(renderWorkspace()).toContain("Dashboard");
    auth.user = null;
    expect(renderWorkspace()).toContain("Dashboard");
  });

  it("keeps the unauthenticated login English", () => {
    auth.user = null;
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <UiLocaleProvider>
          <Login />
        </UiLocaleProvider>
      </MemoryRouter>,
    );
    expect(html).toContain("Sign in");
    expect(html).toContain("Password");
    expect(html).not.toContain("Iniciar sesión");
  });
});
