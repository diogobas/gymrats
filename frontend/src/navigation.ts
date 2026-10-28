import type { Route } from "./router";
import type { IndexDocument } from "./types";

export function selectedYear(index: IndexDocument, route: Route): number | null {
  if (route.view === "month") {
    const month = route.month ?? index.latest_month;
    return month ? Number(month.slice(0, 4)) : index.latest_year;
  }
  return route.view === "season" ? route.year ?? index.latest_year : index.latest_year;
}

export function monthsOfYear(index: IndexDocument, year: number | null) {
  return index.months.filter(item => item.year === year)
    .sort((a, b) => a.month.localeCompare(b.month));
}

export function monthHref(index: IndexDocument, year: number | null): string {
  const month = monthsOfYear(index, year).at(-1)?.month;
  return month ? `#/mes/${month}` : "#/";
}
