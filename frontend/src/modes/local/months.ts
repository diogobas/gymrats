export function monthOptions(now = new Date()): { month: string; provisional: boolean }[] {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Toronto", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const part = (type: string) => parts.find(value => value.type === type)!.value;
  const current = `${part("year")}-${part("month")}`;
  return Array.from({ length: 12 }, (_, i) => `2026-${String(i + 1).padStart(2, "0")}`)
    .filter(month => month < current || (month === current && Number(part("day")) > 1))
    .map(month => ({ month, provisional: month === current }));
}
