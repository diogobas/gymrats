/**
 * Portuguese text and pt-BR numbers.
 *
 * The one piece of prose the site does NOT build is the tiebreak sentence:
 * that arrives ready in the JSON, so the explanation shown to the group is the
 * same one the tally emitted.
 */

const MONTH_NAMES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
] as const;

const SHORT_MONTH_NAMES = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
] as const;

function monthIndex(month: string): number {
  return Number(month.slice(5, 7)) - 1;
}

/** "2026-06" -> "junho de 2026" */
export function monthLabel(month: string): string {
  return `${MONTH_NAMES[monthIndex(month)] ?? month} de ${month.slice(0, 4)}`;
}

/** "2026-06" -> "jun" */
export function shortMonthLabel(month: string): string {
  return SHORT_MONTH_NAMES[monthIndex(month)] ?? month;
}

const decimal = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const integer = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

export function formatDecimal(value: number | null | undefined): string {
  return value == null ? "—" : decimal.format(value);
}

export function formatInteger(value: number | null | undefined): string {
  return value == null ? "—" : integer.format(value);
}

export function formatKm(value: number | null | undefined): string {
  return value == null ? "—" : `${decimal.format(value)} km`;
}

/** The label already comes formatted ("31h01"); this only guards the null. */
export function formatDuration(label: string | null | undefined): string {
  return label ?? "—";
}

/** An ISO timestamp from the publisher -> "28/07/2026, 15:17". */
export function formatTimestamp(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(when);
}

/** ["a", "b", "c"] -> "a, b e c" */
export function joinNames(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

export function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many;
}
