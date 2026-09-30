import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { UiLocaleProvider } from "./UiLocaleProvider";
import Sidebar from "../components/Sidebar";
import InvestmentPortfolio from "../pages/InvestmentPortfolio";
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
          <InvestmentPortfolio />
        </UiLocaleProvider>
      </MemoryRouter>,
    );

  it("renders profile languages, user switches and logout without retained locale", () => {
    auth.user = { locale: "es" };
    expect(renderWorkspace()).toContain("Resumen");
    expect(renderWorkspace()).toContain("Las inversiones no están disponibles");
    auth.user = { locale: "pt" };
    expect(renderWorkspace()).toContain("Resumo");
    expect(renderWorkspace()).not.toContain("Las inversiones");
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
