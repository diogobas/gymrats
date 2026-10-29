import { useState } from "react";
import { source } from "../data/current";
import { joinNames, monthLabel } from "../format";
import { monthsOfYear } from "../navigation";
import type { IndexDocument, IndexMonth, MonthStanding } from "../types";
import { useAsync } from "../useAsync";
import { MonthPicker } from "./MonthPicker";
import { ProvisionalNotice } from "./ProvisionalNotice";
import { MonthTable } from "./MonthTable";
import { Empty, Failure, Loading } from "./Status";
import { TiebreakSummary, UnresolvedTies } from "./Tiebreaks";

function tiedRows(standings: readonly MonthStanding[]) {
  return standings
    .filter((row) => row.tiebreak !== null)
    .map((row) => ({ name: row.name, tiebreak: row.tiebreak! }));
}

function TalliedMonth({ month, categoryPath }: { month: string; categoryPath?: string }) {
  const doc = useAsync(() => source.month(month, categoryPath), [month, categoryPath]);
  const [open, setOpen] = useState<string | null>(null);

  if (doc.status === "loading") return <Loading what={monthLabel(month)} />;
  if (doc.status === "error") return <Failure error={doc.error} />;

  const { value } = doc;
  return (
    <>
      <ProvisionalNotice info={value} />
      {value.official_source && (
        <p className="note">
          Classificação da <a href={value.official_source} target="_blank" rel="noreferrer">planilha oficial</a>,
          incluindo a ordem dos empates. Valores não preservados na fonte aparecem como “—”.
        </p>
      )}
      {value.ignore_hustle && (
        <p className="note" role="status">
          <strong>Hustle desconsiderado neste mês.</strong> A pontuação soma apenas
          as posições em dias ativos e calorias. Zero hustle não exclui participantes.
        </p>
      )}
      {value.standings.length > 0 ? (
        <MonthTable standings={value.standings} open={open} onToggle={setOpen} />
      ) : (
        <Empty>Nenhum classificado: todos os participantes têm zero hustle nos dados publicados deste mês.</Empty>
      )}

      <p className="legend">
        {value.standings.some(row => row.positions.duration != null)
          ? "H hustle points · D dias ativos · T duração · C calorias. A pontuação do mês é a soma das quatro posições"
          : value.ignore_hustle
          ? "H — desconsiderado · D dias ativos · C calorias. A pontuação soma as duas posições"
          : "H hustle points · D dias ativos · C calorias. A pontuação do mês é a soma das três posições"}
        {"; menor soma lidera. Toque numa linha para ver os valores."}
      </p>

      <TiebreakSummary rows={tiedRows(value.standings)} expanded={open} />
      <UnresolvedTies groups={value.unresolved_ties} />

      {value.excluded.length > 0 && (
        <section className="panel">
          <h2 className="panel__title">Fora da apuração</h2>
          <p>
            {joinNames(value.excluded.map((item) => item.name))} ficaram com 0 hustle
            points no mês e saem antes do ranqueamento, sem ocupar posição.
          </p>
        </section>
      )}
    </>
  );
}

/**
 * A month from before the system existed.
 *
 * Only the finishing order was kept, and it lives in the season columns --
 * there is no month document to fetch. Saying so is better than an empty
 * screen: the reader can see the month counted, and why it looks thinner.
 */
function HistoryMonth({ entry }: { entry: IndexMonth }) {
  const doc = useAsync(() => source.season(entry.year), [entry.year]);

  if (doc.status === "loading") return <Loading what={monthLabel(entry.month)} />;
  if (doc.status === "error") return <Failure error={doc.error} />;

  const order = doc.value.standings
    .filter((row) => !row.imputed_months.includes(entry.month))
    .map((row) => ({ name: row.name, position: row.by_month[entry.month] ?? 0 }))
    .sort((a, b) => a.position - b.position);

  return (
    <>
      <p className="note">
        Apurado à mão, antes do sistema existir. As tabelas daquele mês não foram
        guardadas — só a ordem final, que é o que o acumulado do ano usa.
      </p>
      <ol className="standings standings--plain">
        {order.map((row) => (
          <li key={row.name}>
            <span className="cell cell--pos">{row.position}</span>
            <span className="cell cell--name">{row.name}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

export function MonthView({ index, month, categoryPath, category }: { index: IndexDocument; month: string; categoryPath?: string; category?: string }) {
  const entry = index.months.find((item) => item.month === month);

  return (
    <section>
      <MonthPicker months={monthsOfYear(index, Number(month.slice(0, 4)))} current={month} category={category} />
      <h1 className="title">{monthLabel(month)}</h1>
      {entry ? (
        entry.detail ? (
          <TalliedMonth key={categoryPath} month={month} categoryPath={categoryPath} />
        ) : (
          <HistoryMonth entry={entry} />
        )
      ) : (
        <Empty>Esse mês ainda não foi apurado.</Empty>
      )}
    </section>
  );
}
