import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NotFound from "./NotFound";

const h = vi.hoisted(() => ({ link: vi.fn() }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", async original => {
  const router = await original<typeof import("react-router-dom")>();
  return { ...router, Link: (props: import("react-router-dom").LinkProps) => {
    h.link(props);
    return <router.Link {...props} />;
  } };
});

beforeEach(() => vi.clearAllMocks());
describe("NotFound", () => {
  it("uses the router Link for home navigation rather than a document navigation anchor", () => {
    const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/missing"]}><NotFound /></MemoryRouter>);
    expect(h.link).toHaveBeenCalledWith(expect.objectContaining({ to: "/", children: "Return to Home" }));
    expect(html).toContain('href="/"');
    expect(html).toContain("404");
    expect(html).toContain("Return to Home</a>");
  });
});
