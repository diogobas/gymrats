import { useEffect, useState, type FormEvent } from "react";
import { formatTimestamp } from "../format";
import CloseMonthPanel from "./CloseMonthPanel";
import { request, RequestError, type Run } from "./refreshApi";

type Session = { token: string; expires: number };
const endpoint = (import.meta.env.VITE_REFRESH_URL ?? "").replace(/\/$/, "");

export function runLabel(run: Run): string {
  if (run.status !== "completed") return run.status === "in_progress" ? "Atualizando dados e publicando…" : "Aguardando execução…";
  if (run.conclusion === "success") return "Atualização concluída";
  if (run.conclusion === "cancelled") return "Atualização cancelada";
  return "A atualização não foi concluída. Consulte os detalhes.";
}

export default function RefreshPanel() {
  // Credentials and session tokens never enter persistent browser storage.
  const [session, setSession] = useState<Session | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [pending, setPending] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function handleError(reason: unknown) {
    if (reason instanceof RequestError && reason.status === 401) setSession(null);
    setError(reason instanceof RequestError ? reason.message : "Não foi possível conectar. Confira sua conexão e o GitHub Actions antes de tentar novamente.");
  }

  useEffect(() => {
    if (!session) { setRuns([]); setPending(null); return; }
    let disposed = false;
    const refresh = async () => {
      try {
        const data = await request<{ runs: Run[] }>("/runs", session.token);
        if (!disposed) { setRuns(data.runs); setError(""); }
      } catch (reason) { if (!disposed) handleError(reason); }
    };
    void refresh();
    const poll = window.setInterval(() => { void refresh(); }, 10000);
    const expiry = window.setTimeout(() => { setSession(null); setError("Sessão expirada. Entre novamente."); }, Math.max(0, session.expires - Date.now()));
    return () => { disposed = true; clearInterval(poll); clearTimeout(expiry); };
  }, [session]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true); setError(""); setNotice("");
    try {
      const data = await request<{ token: string; expires_in: number }>("/login", undefined, { username: fields.get("username"), password: fields.get("password") });
      form.reset();
      setSession({ token: data.token, expires: Date.now() + data.expires_in * 1000 });
    } catch (reason) { handleError(reason); }
    finally { setBusy(false); }
  }

  async function start() {
    if (!session || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const data = await request<{ run: Run; existing: boolean }>("/refresh", session.token, {});
      setPending(data.run);
      setNotice(data.existing ? "Já há uma atualização em andamento. Acompanhe abaixo." : "Atualização solicitada. Você pode fechar esta página; o processo continua.");
    } catch (reason) { handleError(reason); }
    finally { setBusy(false); }
  }

  const tracked = pending ? runs.find(run => run.id === pending.id) ?? pending : null;
  const active = runs.some(run => run.status !== "completed") || !!(tracked && tracked.status !== "completed");
  const displayed = tracked ? [tracked, ...runs.filter(run => run.id !== tracked.id)] : runs;
  return <section className="refresh-panel panel" aria-labelledby="refresh-title">
    <h1 id="refresh-title">Atualizar o site</h1>
    <p>Consultar os rankings, validar os dados e publicar as novidades.</p>
    {!endpoint ? <p role="status">A atualização manual ainda não foi configurada.</p>
      : !session ? <form onSubmit={login}>
        <label className="field"><span>Usuário</span><input name="username" autoComplete="username" required maxLength={200} disabled={busy} /></label>
        <label className="field"><span>Senha</span><input name="password" type="password" autoComplete="current-password" required maxLength={1000} disabled={busy} /></label>
        <button className="button" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</button>
      </form> : <>
        <p className="note">A coleta usa o corte até ontem, no horário de São Paulo, conforme a atualização diária.</p>
        <div className="refresh-panel__actions">
          <button type="button" className="button" disabled={busy || active} onClick={() => { void start(); }}>{busy ? "Solicitando…" : active ? "Atualização em andamento" : "Atualizar agora"}</button>
          <button type="button" className="button button--ghost" disabled={busy} onClick={() => { setSession(null); setNotice(""); setError(""); }}>Sair</button>
        </div>
        <p className="hint">O processo pode levar alguns minutos. O andamento é consultado a cada 10 segundos.</p>
        <ul className="panel__list" aria-label="Atualizações recentes">
          {displayed.map(run => <li key={run.id}>
            <strong>{run.title && `${run.title} · `}{runLabel(run)}</strong>
            <p className="note">{formatTimestamp(run.created_at)} · <a href={run.url} target="_blank" rel="noopener noreferrer">Ver execução</a></p>
            {run.status === "completed" && run.conclusion === "success" && <a href={import.meta.env.BASE_URL}>Abrir site atualizado</a>}
          </li>)}
        </ul>
        <CloseMonthPanel token={session.token} disabled={busy || active} onBusy={setBusy}
          onError={handleError} onStarted={run => {
            setPending(run);
            setNotice("Fechamento solicitado. Aguarde a conclusão da execução e da publicação antes de conferir o placar.");
          }} />
      </>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="status--error" role="alert">{error}</p>}
    <p><a href="#/">Voltar ao placar</a></p>
  </section>;
}
