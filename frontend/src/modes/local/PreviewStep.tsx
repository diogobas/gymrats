import { useEffect, useState } from "react";
import { MonthTable } from "../../components/MonthTable";
import { SeasonTable } from "../../components/SeasonView";
import { TiebreakSummary, UnresolvedTies } from "../../components/Tiebreaks";
import { monthLabel, plural } from "../../format";
import { api } from "./api";
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
      setResult(await api.commit(month, draft, batch));
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
          <h2 className="panel__title">Fechado</h2>
          <p>
            As tabelas foram gravadas em <code>{result.month_path}</code> e os JSONs
            do site foram regerados. Falta commitar no git para o site publicar.
          </p>
          <p>
            <a className="button button--small" href={api.csvUrl(month)}>
              Baixar CSV
            </a>
          </p>
        </div>
      ) : (
        <p className="note">
          Nada foi gravado ainda. É isso que o grupo vai ver.
          {issues.length > 0 &&
            ` ${issues.length} ${plural(issues.length, "linha segue destacada", "linhas seguem destacadas")} — dá para fechar assim mesmo.`}
        </p>
      )}

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

      <div className="actions">
        <button type="button" className="button button--ghost" onClick={onBack}>
          Voltar para a conferência
        </button>
        {!committed && (
          <button type="button" className="button" disabled={busy} onClick={commit}>
            {busy ? "Fechando…" : "Fechar o mês"}
          </button>
        )}
      </div>
    </section>
  );
}
