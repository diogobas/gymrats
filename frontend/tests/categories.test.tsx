import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { MonthPicker } from "../src/components/MonthPicker";
import { SeasonTable } from "../src/components/SeasonView";
import { staticSource } from "../src/data/staticSource";
import { parseRoute, routeHref } from "../src/router";
import type { SeasonDocument } from "../src/types";

afterEach(() => vi.unstubAllGlobals());

it("keeps female selection in shared links and monthly navigation", () => {
  for (const hash of ["#/mes/2024-08?categoria=women", "#/ano/2024?categoria=women"]) {
    expect(routeHref(parseRoute(hash))).toBe(hash);
  }
  const html = renderToStaticMarkup(<MonthPicker
    months={[{ month: "2024-08", year: 2024, detail: true }]}
    current="2024-08" category="women"
  />);
  expect(html).toContain('#/mes/2024-08?categoria=women');
});

it("fetches female files independently from the male default", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetcher);
  await staticSource.month("2024-11", "categories/2024-women");
  await staticSource.season(2024, "categories/2024-women");
  await staticSource.season(2024);
  expect(fetcher.mock.calls.map(call => call[0])).toEqual([
    "/data/categories/2024-women/months/2024-11.json",
    "/data/categories/2024-women/season/2024.json",
    "/data/season/2024.json",
  ]);
});

it("explains the female coverage and keeps unavailable December out of the season", () => {
  const doc: SeasonDocument = JSON.parse(readFileSync(
    new URL("../public/data/categories/2024-women/season/2024.json", import.meta.url), "utf8",
  ));
  const html = renderToStaticMarkup(<SeasonTable doc={doc} />);
  expect(doc.months).toEqual(["2024-08", "2024-09", "2024-10", "2024-11"]);
  expect(html).toContain("dezembro feminino ainda não está disponível");
  expect(html).toContain("Ludimilla");
  expect(html).not.toContain("Diogo");
});
