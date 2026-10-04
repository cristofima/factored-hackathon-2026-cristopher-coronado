import { describe, expect, it } from "vitest";
import { formatDateTime } from "./dateTime";

describe("support case date/time display", () => {
  it.each([["en", "Oct"], ["es", "oct"], ["pt", "out."]])("uses a consistent localized 24-hour format in %s", (locale, month) => {
    const value = "2026-10-03T23:35:07";
    expect(formatDateTime(value, locale)).toBe(`3 ${month} 2026, 23:35`);
    expect(formatDateTime(value, locale, "date-time")).toBe(`3 ${month} 2026, 23:35`);
    expect(formatDateTime(value, locale, "date-time-seconds")).toBe(`3 ${month} 2026, 23:35:07`);
    expect(formatDateTime("2026-10-03T00:05:09", locale, "date-time-seconds")).toBe(`3 ${month} 2026, 00:05:09`);
  });

  it("displays equivalent UTC and offset timestamps in the same local timezone", () => {
    expect(formatDateTime("2026-10-04T04:35:07Z", "es", "date-time-seconds"))
      .toBe(formatDateTime("2026-10-03T23:35:07-05:00", "es", "date-time-seconds"));
  });

  it.each(["en", "es", "pt"])("preserves financial calendar dates in %s without timezone conversion", locale => {
    expect(formatDateTime("2026-10-03", locale, "YYYY-MM-DD")).toBe("2026-10-03");
    expect(formatDateTime("2026-10-03T23:35:07-05:00", locale, "YYYY-MM-DD")).toBe("2026-10-03");
  });

  it("falls back to English for an unsupported profile locale", () => {
    expect(formatDateTime("2026-10-03T23:35:07", "fr")).toBe("3 Oct 2026, 23:35");
  });
});
