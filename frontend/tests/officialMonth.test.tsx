import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { MonthTable } from "../src/components/MonthTable";
import { SeasonTable } from "../src/components/SeasonView";
import type { MonthDocument, SeasonDocument } from "../src/types";

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

it("shows the historical 15% calorie bonus instead of today's 20%", () => {
  const doc: MonthDocument = JSON.parse(readFileSync(
    new URL("../public/data/months/2025-02.json", import.meta.url), "utf8",
  ));
  const html = renderToStaticMarkup(
    <MonthTable standings={doc.standings} open="Isadora" onToggle={() => {}} />,
  );
  expect(html).toContain("+15% →");
  expect(html).not.toContain("+20% →");
  expect(html).toContain("Duração · 4º");
});

it("renders the official season scope, historical absence scores and corrected order", () => {
  const doc: SeasonDocument = JSON.parse(readFileSync(
    new URL("../public/data/season/2025.json", import.meta.url), "utf8",
  ));
  const html = renderToStaticMarkup(<SeasonTable doc={doc} />);
  expect(doc.standings).toHaveLength(20);
  expect(html).toContain(doc.official_source);
  expect(html).toContain("Pontuações históricas de ausência");
  expect(html).toContain("18 pontos");
  expect(html).toContain("13 pontos");
  expect(html).not.toContain("Ludimilla");
  expect(html.indexOf("Thamyres")).toBeLessThan(html.indexOf("Jorge Luiz"));
});
