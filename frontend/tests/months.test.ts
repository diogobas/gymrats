import { expect, it } from "vitest";
import { monthOptions } from "../src/modes/local/months";

it("offers closed months and the current month as a distinct partial snapshot", () => {
  const options = monthOptions(new Date("2026-10-27T16:00:00Z"));
  expect(options).toHaveLength(10);
  expect(options.at(-1)).toEqual({ month: "2026-10", provisional: true });
  expect(options.filter(option => !option.provisional)).toHaveLength(9);
});

it("uses Toronto's date and waits for a complete day in the new month", () => {
  // It is still October 31 in Toronto.
  expect(monthOptions(new Date("2026-11-01T02:00:00Z")).at(-1))
    .toEqual({ month: "2026-10", provisional: true });
  // November 1 has no complete November day to query yet.
  expect(monthOptions(new Date("2026-11-01T16:00:00Z")).at(-1))
    .toEqual({ month: "2026-10", provisional: false });
  expect(monthOptions(new Date("2026-11-02T16:00:00Z")).at(-1))
    .toEqual({ month: "2026-11", provisional: true });
});
