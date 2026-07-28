import { useState } from "react";
import { source } from "../data/current";
import { joinNames, monthLabel, plural, shortMonthLabel } from "../format";
import type { SeasonDocument, SeasonStanding } from "../types";
import { useAsync } from "../useAsync";
import { Failure, Loading } from "./Status";
import { TiebreakBadge, TiebreakNote, TiebreakSummary, UnresolvedTies } from "./Tiebreaks";

function Imputed({ row }: { row: SeasonStanding }) {
  if (row.imputed_months.length === 0) return null;
  const months = row.imputed_months.map(monthLabel);
  return (
    <p className="hint">
      Não competiu em {joinNames(months)} —{" "}
      {plural(months.length, "recebeu", "recebeu em cada um")} a posição do último
      colocado daquele mês mais um.
    </p>
  );
}

/**
 * The season, given the document.
 *
 * Split from the fetching so the admin build can render a season that only
 * exists as a preview -- one that has not been written anywhere yet.
 */
export function SeasonTable({ doc }: { doc: SeasonDocument }) {
  const [open, setOpen] = useState<string | null>(null);
  const { months, standings } = doc;
  const opened = standings.find((row) => row.name === open);

  return (
    <>
      <div className="scroller">
        <table className="season">
          <thead>
            <tr>
              <th className="col--pos">#</th>
              <th className="col--name">nome</th>
              <th className="col--total">total</th>
              {months.map((month) => (
                <th key={month}>{shortMonthLabel(month)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {standings.map((row) => {
              const expanded = open === row.name;
              return (
                <tr
                  key={row.name}
                  className={expanded ? "is-open" : undefined}
                  // A whole row is the easy target on a phone; the keyboard
                  // handler is what keeps it usable without one.
                  role="button"
                  tabIndex={0}
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : row.name)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setOpen(expanded ? null : row.name);
                    }
                  }}
                >
                  <td className="col--pos">{row.position}</td>
                  <td className="col--name">
                    {row.name}
                    <TiebreakBadge tiebreak={row.tiebreak} />
                  </td>
                  <td className="col--total">{row.total}</td>
                  {months.map((month) => (
                    <td
                      key={month}
                      className={
                        row.imputed_months.includes(month) ? "is-imputed" : undefined
                      }
                    >
                      {row.by_month[month]}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="legend">
        Números claros são a posição conquistada; os apagados são de meses em que
        a pessoa não competiu.
      </p>

      {opened && (
        <section className="panel">
          <h2 className="panel__title">
            {opened.position}º · {opened.name} · {opened.total} pontos
          </h2>
          <Imputed row={opened} />
          <TiebreakNote tiebreak={opened.tiebreak} />
        </section>
      )}

      <TiebreakSummary
        rows={standings
          .filter((row) => row.tiebreak !== null)
          .map((row) => ({ name: row.name, tiebreak: row.tiebreak! }))}
        expanded={open}
      />
      <UnresolvedTies groups={doc.unresolved_ties} />
    </>
  );
}

export function SeasonView({ year }: { year: number }) {
  const doc = useAsync(() => source.season(year), [year]);

  if (doc.status === "loading") return <Loading what={`o acumulado de ${year}`} />;
  if (doc.status === "error") return <Failure error={doc.error} />;

  return (
    <section>
      <h1 className="title">Acumulado de {year}</h1>
      <p className="note">
        Uma coluna por mês, com a posição final. O total é a soma — menor total
        lidera.
      </p>
      <SeasonTable doc={doc.value} />
    </section>
  );
}
