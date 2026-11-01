import { useEffect, useState } from "react";
import { monthLabel } from "../format";
import type { IndexMonth, MonthDocument } from "../types";
import { MonthTable } from "./MonthTable";
import { TiebreakSummary, UnresolvedTies } from "./Tiebreaks";
import { request, RequestError, type Run } from "./refreshApi";

type Review = { revision: string; months: IndexMonth[]; month?: MonthDocument };

export function ReviewedMonth({ document }: { document: MonthDocument }) {
  const [open, setOpen] = useState<string | null>(null);
  return <>
    <h3>{monthLabel(document.month)}</h3>
    <p className="note">Dados até {document.data_through?.split("-").reverse().join("/")}. Toque nas linhas para conferir os valores e bônus.</p>
    <MonthTable standings={document.standings} open={open} onToggle={setOpen} />
    <TiebreakSummary rows={document.standings.filter(row => row.tiebreak !== null).map(row => ({ name: row.name, tiebreak: row.tiebreak! }))} expanded={open} />
    <UnresolvedTies groups={document.unresolved_ties} />
    {!!document.excluded.length && <p className="note">Fora da apuração por 0 hustle: {document.excluded.map(item => item.name).join(", ")}.</p>}
  </>;
}

export default function CloseMonthPanel({ token, disabled, onBusy, onStarted, onError }: {
  token: string; disabled: boolean; onBusy: (busy: boolean) => void;
  onStarted: (run: Run) => void; onError: (reason: unknown) => void;
}) {
  const [months, setMonths] = useState<IndexMonth[]>([]);
  const [month, setMonth] = useState("");
  const [review, setReview] = useState<Review | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function failed(reason: unknown) {
    setError(reason instanceof RequestError ? reason.message : "Não foi possível carregar a conferência. Tente novamente.");
    if (reason instanceof RequestError && reason.status === 401) onError(reason);
  }

  useEffect(() => {
    let disposed = false;
    request<Review>("/review", token).then(data => {
      if (!disposed) { setMonths(data.months); setMonth(data.months[0]?.month ?? ""); }
    }).catch(reason => { if (!disposed) failed(reason); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [token]);

  async function loadReview() {
    setLoading(true); setError(""); setReview(null); setConfirmed(false);
    try {
      const data = await request<Review>(month ? `/review?month=${month}` : "/review", token);
      setMonths(data.months); setReview(data.month ? data : null);
      if (!data.month) setMonth(data.months[0]?.month ?? "");
    } catch (reason) { failed(reason); }
    finally { setLoading(false); }
  }

  async function close() {
    if (!review?.month || !confirmed || disabled || loading) return;
    onBusy(true); setError("");
    try {
      const data = await request<{ run: Run }>("/close", token, { month: review.month.month, revision: review.revision, confirmed: true });
      setReview(null); setConfirmed(false); onStarted(data.run);
    } catch (reason) {
      // A failed or stale confirmation must never be automatically retried.
      setReview(null); setConfirmed(false); failed(reason);
    } finally { onBusy(false); }
  }

  return <section className="close-month" aria-labelledby="close-month-title">
    <h2 id="close-month-title">Revisar e fechar mês</h2>
    <p>Confira o resultado completo antes de torná-lo definitivo. O fechamento também recalcula e publica o acumulado do ano.</p>
    {loading && <p role="status">Carregando conferência…</p>}
    {!loading && !months.length && !error && <p>Nenhum mês aguardando fechamento.</p>}
    {!!months.length && <label className="field"><span>Mês aguardando fechamento</span>
      <select value={month} disabled={disabled || loading} onChange={event => { setMonth(event.target.value); setReview(null); setConfirmed(false); setError(""); }}>
        {months.map(item => <option key={item.month} value={item.month}>{monthLabel(item.month)}</option>)}
      </select>
    </label>}
    <button type="button" className="button button--ghost" disabled={disabled || loading} onClick={() => { void loadReview(); }}>{month ? "Abrir / atualizar conferência" : "Consultar meses"}</button>
    {review?.month && <div key={review.revision + review.month.month}>
      <ReviewedMonth document={review.month} />
      {!review.month.unresolved_ties.length && <>
        <label className="close-month__confirmation"><input type="checkbox" checked={confirmed} disabled={disabled} onChange={event => setConfirmed(event.target.checked)} />
          <span>Conferi os valores, bônus, participantes e desempates de {monthLabel(review.month.month)} e confirmo o fechamento definitivo.</span>
        </label>
        <button type="button" className="button" disabled={disabled || !confirmed} onClick={() => { void close(); }}>Confirmar e fechar {monthLabel(review.month.month)}</button>
        <p className="hint">Se os dados mudarem, será necessário abrir a conferência novamente. Esta ação não substitui meses já fechados.</p>
      </>}
    </div>}
    {error && <p role="alert" className="status--error">{error}</p>}
  </section>;
}
