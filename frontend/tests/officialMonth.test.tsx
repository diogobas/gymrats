import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { MonthTable } from "../src/components/MonthTable";
import { SeasonTable } from "../src/components/SeasonView";
import type { MonthDocument, SeasonDocument } from "../src/types";

it("publishes only closed months in the annual standings", () => {
  const doc: SeasonDocument = JSON.parse(readFileSync(new URL("../public/data/season/2026.json", import.meta.url), "utf8"));
  const index = JSON.parse(readFileSync(new URL("../public/data/index.json", import.meta.url), "utf8"));
  expect(doc.closed_only).toBe(true);
  expect(doc.provisional).toBeUndefined();
  expect(doc.months).toEqual(index.months.filter((item: { year: number; provisional?: boolean }) => item.year === 2026 && !item.provisional).map((item: { month: string }) => item.month));
  for (const row of doc.standings) {
    expect(Object.keys(row.by_month)).toEqual(doc.months);
    expect(row.total).toBe(Object.values(row.by_month).reduce((sum, value) => sum + value, 0));
  }
  const html = renderToStaticMarkup(<SeasonTable doc={doc} />);
  expect(html).toContain("Somente meses oficialmente fechados");
  expect(html).not.toContain("Acumulado provisório");
});

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

it("renders the official season scope and uniform absence rule", () => {
  const doc: SeasonDocument = JSON.parse(readFileSync(
    new URL("../public/data/season/2025.json", import.meta.url), "utf8",
  ));
  const html = renderToStaticMarkup(<SeasonTable doc={doc} />);
  expect(doc.standings).toHaveLength(20);
  expect(html).toContain(doc.official_source);
  expect(html).toContain("Quem não competiu recebe a posição do último colocado do mês mais um");
  expect(html).not.toContain("Pontuações históricas de ausência");
  expect(html).not.toContain("Ludimilla");
  expect(html.indexOf("Thamyres")).toBeLessThan(html.indexOf("Jorge Luiz"));
});
