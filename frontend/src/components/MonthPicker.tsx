import { shortMonthLabel } from "../format";
import type { IndexMonth } from "../types";

/**
 * Every month of the season, including the ones tallied by hand.
 *
 * Those are shown and reachable: hiding half the season would be stranger than
 * showing a month whose leaderboards no longer exist. The screen says which
 * kind it is.
 */
export function MonthPicker({
  months,
  current,
  category,
}: {
  months: readonly IndexMonth[];
  current: string;
  category?: string;
}) {
  return (
    <nav className="picker" aria-label="Escolher mês">
      {months.map((item) => (
        <a
          key={item.month}
          href={`#/mes/${item.month}${category ? `?categoria=${category}` : ""}`}
          className={`chip${item.month === current ? " is-current" : ""}${
            item.detail ? "" : " chip--history"
          }`}
          title={item.pending_review ? "Aguardando fechamento" : item.provisional ? "Mês em andamento" : undefined}
          aria-current={item.month === current ? "page" : undefined}
        >
          {shortMonthLabel(item.month)}{item.pending_review ? " · revisar" : item.provisional ? " · parcial" : ""}
        </a>
      ))}
    </nav>
  );
}
