import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Link } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Button } from "./button";

describe("Button composition", () => {
  it.each([false, true])("slots an SPA link with loading=%s without a single-child error", loading => {
    const html = renderToStaticMarkup(
      <MemoryRouter><Button asChild loading={loading}><Link to="/support-cases">Cases</Link></Button></MemoryRouter>,
    );
    expect(html).toContain('href="/support-cases"');
    expect(html).toContain("Cases</a>");
    expect(html).not.toContain("<button");
    expect(html.includes("animate-spin")).toBe(loading);
    if (loading) expect(html.indexOf("<svg")).toBeLessThan(html.indexOf("Cases"));
  });

  it.each([false, true])("preserves native button children with loading=%s", loading => {
    const html = renderToStaticMarkup(<Button loading={loading} disabled={false}>Submit</Button>);
    expect(html).toContain("Submit</button>");
    expect(html.includes('disabled=""')).toBe(loading);
    expect(html.includes("animate-spin")).toBe(loading);
  });

  it("keeps slotted button props and disables loading despite disabled=false", () => {
    const html = renderToStaticMarkup(
      <Button asChild loading disabled={false} aria-label="Send"><button type="submit" className="child-style">Send</button></Button>,
    );
    expect(html).toContain('type="submit"');
    expect(html).toContain('aria-label="Send"');
    expect(html).toContain("child-style");
    expect(html).toContain('disabled=""');
  });
});
