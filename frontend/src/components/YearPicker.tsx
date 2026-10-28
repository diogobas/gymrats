import { monthHref } from "../navigation";
import type { IndexDocument } from "../types";

export function YearPicker({ index, year, view }: {
  index: IndexDocument;
  year: number | null;
  view: "month" | "season";
}) {
  if (index.years.length === 0) return null;
  const available = year !== null && index.years.includes(year);

  return (
    <label className="year-picker">
      Ano
      <select value={available ? String(year) : ""} onChange={event => {
        const selected = Number(event.target.value);
        window.location.hash = view === "season" ? `#/ano/${selected}` : monthHref(index, selected);
      }}>
        {!available && <option value="" disabled>Escolha um ano</option>}
        {[...index.years].sort((a, b) => b - a).map(value => (
          <option key={value} value={value}>{value}</option>
        ))}
      </select>
    </label>
  );
}
