import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { MonthTable } from "../src/components/MonthTable";
import type { MonthDocument } from "../src/types";

it("shows four scoring positions and preserves the official January order", () => {
  const doc: MonthDocument = JSON.parse(readFileSync(
    new URL("../public/data/months/2025-01.json", import.meta.url), "utf8",
  ));
  const html = renderToStaticMarkup(
    <MonthTable standings={doc.standings} open="Ludimilla" onToggle={() => {}} />,
  );
  expect(html).toContain("standings--four");
  expect(html).toContain('title="duração"');
  expect(html).toContain("Duração · 1º");
  expect(html).toContain("A duração pontua neste mês");
  expect(html).not.toContain("Distância e duração não pontuam");
  expect(html.indexOf("Ludimilla")).toBeLessThan(html.indexOf("Arthur"));
});
