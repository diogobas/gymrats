import { useEffect, useState } from "react";
import { monthOptions } from "./months";
import { api } from "./api";
import { UploadStep } from "./UploadStep";
import type { CollectionRun, SessionState } from "./types";

export function DataStep({ month, onMonth, onBatch, onRun }: {
  month: string; onMonth: (month: string) => void;
  onBatch: (id: string) => void; onRun: (id: string) => void;
}) {
  const [session, setSession] = useState<SessionState | null>(null);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [runs, setRuns] = useState<CollectionRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = monthOptions().find(option => option.month === month);
  const active = runs.some(run => run.status === "running");
  useEffect(() => {
    let alive = true;
    api.session().then(value => { if (alive) { setSession(value); setPending(!!value.code_pending); } },
      reason => { if (alive) setError(String(reason)); });
    const refresh = () => api.runs().then(value => { if (alive) setRuns(value); },
      reason => { if (alive) setError(String(reason)); });
    void refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);
  async function work(action: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  return <section>
    <h1 className="title">Apurar um mês</h1>
    <p className="note"><strong>Gymrats 2026!</strong> · clube 2504035</p>
    <label className="field"><span>Mês</span>
      <select value={month} onChange={event => onMonth(event.target.value)}>
        {monthOptions().map(option => <option key={option.month} value={option.month}>{option.month}{option.provisional ? " · em andamento" : ""}</option>)}
      </select>
    </label>
    <p className="hint">{selected?.provisional ? "Prévia parcial até ontem. O mês permanece em andamento; o acumulado também será provisório." : "Distância e duração anuais: de 1º de janeiro até o último dia do mês selecionado."}</p>
    <section className="panel">
      <h2 className="panel__title">Conexão com GymRats</h2>
      {session?.connected ? <>
        <p>Conectado como {session.account?.name}.</p>
        <button className="button button--small" disabled={busy || active} onClick={() => void work(async () => {
          setSession(await api.disconnect()); setPending(false);
        })}>Desconectar</button>
      </> : <>
        <p>{session?.message ?? "Verificando conexão…"}</p>
        <form onSubmit={event => { event.preventDefault(); void work(async () => {
          await api.requestCode(email); setPending(true); setCode("");
        }); }}>
          <label className="field"><span>E-mail da conta existente</span>
            <input type="email" required autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} />
          </label>
          <button className="button button--small" disabled={busy}>Solicitar código</button>
        </form>
        {pending && <form onSubmit={event => { event.preventDefault(); void work(async () => {
          setSession(await api.verifyCode(code)); setCode(""); setPending(false);
        }); }}>
          <label className="field"><span>Código recebido por e-mail</span>
            <input required autoComplete="one-time-code" value={code} onChange={event => setCode(event.target.value)} />
          </label>
          <button className="button button--small" disabled={busy}>Conectar</button>
        </form>}
      </>}
    </section>
    <button className="button" disabled={busy || active || !session?.connected || !selected}
      onClick={() => void work(async () => { const run = await api.collect(month, selected?.provisional ?? false); setRuns(old => [run, ...old]); })}>
      {active ? "Coletando…" : "Buscar dados do GymRats"}
    </button>
    {error && <p className="panel panel--warn" role="alert">{error}</p>}
    {runs.length > 0 && <section className="panel">
      <h2 className="panel__title">Coletas e rascunhos</h2>
      <ul className="panel__list">{runs.map(run => <li key={run.id} className="pending">
        <div><strong>{run.month}{run.provisional && " · em andamento"}</strong> · {run.completed}/7 consultas
          <p>{({ running: "Em andamento", complete: "Pronto para conferir", partial: "Coleta parcial", interrupted: "Interrompida" })[run.status]}</p>
          {run.error && <p role="alert">{run.error}</p>}
        </div>
        {run.status === "complete" && <button className="button button--small" onClick={() => onRun(run.id)}>Conferir / retomar</button>}
      </li>)}</ul>
      <p className="hint">Uma nova tentativa cria outra coleta e preserva as correções anteriores. Ex-membros podem faltar na API; confira os participantes.</p>
    </section>}
    <details><summary>Alternativa: usar screenshots</summary>
      <UploadStep month={month} onMonth={onMonth} onBatch={onBatch} />
    </details>
  </section>;
}
