import { useEffect, useState } from "react";
import { ProvisionalNotice } from "../../components/ProvisionalNotice";
import { MonthTable } from "../../components/MonthTable";
import { SeasonTable } from "../../components/SeasonView";
import { TiebreakSummary, UnresolvedTies } from "../../components/Tiebreaks";
import { monthLabel, plural } from "../../format";
import { api } from "./api";
import { metricLabel, periodLabel } from "./labels";
import type { Draft, TallyResponse } from "./types";

/**
 * Step three: the standings, before anything is written.
 *
 * Rendered with the very same components the public site uses, from the very
 * same JSON shapes -- so what is on screen here is what the group will see,
 * not an approximation of it.
 */
export function PreviewStep({
  batch,
  month,
  draft,
  onBack,
}: {
  batch: string;
  month: string;
  draft: Draft;
  onBack: () => void;
}) {
  const [result, setResult] = useState<TallyResponse | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [replace, setReplace] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBusy(true);
    api.preview(month, draft).then(
      (response) => {
        setResult(response);
        setBusy(false);
      },
      (reason: Error) => {
        setError(reason.message);
        setBusy(false);
      },
    );
  }, [month, draft]);

  async function commit() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.commit(month, draft, batch, result ?? undefined, replace));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <section>
        <div className="panel panel--warn" role="alert">
          <p>{error}</p>
        </div>
        <button type="button" className="button button--ghost" onClick={onBack}>
          Voltar
        </button>
      </section>
    );
  }

  if (!result) return <p className="status">Calculando…</p>;

  const { month: monthDoc, season, issues, committed } = result;

  return (
    <section>
      <h1 className="title">{monthLabel(month)}</h1>

      {committed ? (
        <div className="panel">
          <h2 className="panel__title">{result.provisional ? "Prévia salva · mês em andamento" : "Apuração salva · publicação pendente"}</h2>
          <p>
            As tabelas foram gravadas em <code>{result.month_path}</code> e os JSONs
            do site foram regerados. Falta commitar no git para o site publicar.
          </p>
          {!result.provisional && <p>
            <a className="button button--small" href={api.csvUrl(month)}>
              Baixar CSV
            </a>
          </p>}
        </div>
      ) : (
        <p className="note">
          Nada foi gravado ainda. É isso que o grupo vai ver.
          {issues.length > 0 &&
            ` ${issues.length} ${plural(issues.length, "linha segue destacada", "linhas seguem destacadas")} — confira os avisos.`}
        </p>
      )}

      {result.annual_end_date && <p className="note">Corte anual: 2026-01-01 a {result.annual_end_date} · revisão {result.revision}</p>}
      {!!result.differences?.length && <details className="panel" open>
        <summary>{result.differences.length} diferenças em relação à apuração anterior</summary>
        <div className="table-scroll"><table><thead><tr><th>Nome</th><th>Métrica</th><th>Período</th><th>Anterior</th><th>Revisado</th></tr></thead>
          <tbody>{result.differences.map((diff, i) => <tr key={i}><td>{diff.name}</td><td>{metricLabel(diff.metric)}</td><td>{periodLabel(diff.period)}</td><td>{diff.previous ?? "ausente"}</td><td>{diff.collected ?? "ausente"}</td></tr>)}</tbody>
        </table></div>
      </details>}
      <ProvisionalNotice info={monthDoc} />
      <h2 className="subtitle">Classificação do mês</h2>
      <MonthTable standings={monthDoc.standings} open={open} onToggle={setOpen} />
      <TiebreakSummary
        rows={monthDoc.standings
          .filter((row) => row.tiebreak !== null)
          .map((row) => ({ name: row.name, tiebreak: row.tiebreak! }))}
        expanded={open}
      />
      <UnresolvedTies groups={monthDoc.unresolved_ties} />

      {monthDoc.excluded.length > 0 && (
        <p className="legend">
          Fora da apuração por 0 hustle:{" "}
          {monthDoc.excluded.map((item) => item.name).join(", ")}.
        </p>
      )}

      <h2 className="subtitle">Acumulado do ano</h2>
      <SeasonTable doc={season} />

      {!committed && result.replacement && <label className="note">
        <input type="checkbox" checked={replace} onChange={event => setReplace(event.target.checked)} />
        Conferi os avisos e confirmo substituir {result.provisional ? "a prévia" : "a apuração"} de {monthLabel(month)}.
      </label>}
      <div className="actions">
        <button type="button" className="button button--ghost" onClick={onBack}>
          Voltar para a conferência
        </button>
        {!committed && (
          <button type="button" className="button" disabled={busy || (!!result.replacement && !replace)} onClick={commit}>
            {busy ? "Salvando…" : result.provisional ? "Salvar prévia do mês" : "Fechar o mês"}
          </button>
        )}
      </div>
    </section>
  );
}
