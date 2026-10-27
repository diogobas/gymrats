import { useEffect, useRef, useState } from "react";
import { monthLabel, plural } from "../../format";
import { api } from "./api";
import { metricLabel, periodLabel } from "./labels";
import { DraftSaver } from "./DraftSaver";
import { TableCard } from "./TableCard";
import type { Draft, DraftTable, Participant } from "./types";

/** Review edits are persisted in order; navigation waits for every write. */

const BLANK_TABLE: DraftTable = {
  key: "?/?",
  label: "tabela nova",
  modality: null,
  period: null,
  sources: [],
  rows: [],
};

export function ReviewStep({
  batch,
  month,
  draft,
  onDraft,
  onDone,
  onBack,
}: {
  batch: string;
  month: string;
  draft: Draft;
  onDraft: (draft: Draft) => void;
  onDone: () => void;
  onBack: () => void;
}) {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saver = useRef<DraftSaver | null>(null);
  if (!saver.current) saver.current = new DraftSaver(draft, next => api.saveDraft(batch, next));
  const version = useRef(0);

  useEffect(() => {
    api.participants().then(setParticipants, () => undefined);
  }, []);

  function save(next: Draft) {
    const current = ++version.current;
    setSaving(true); setError(null);
    void saver.current!.save(next).then(saved => {
      if (version.current === current) { onDraft(saved); setSaving(false); }
    }, reason => {
      setSaving(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    });
  }

  function edit(next: Draft) {
    onDraft(next);
    save(next);
  }

  async function leave(done: () => void) {
    setSaving(true);
    try {
      onDraft(await saver.current!.flush());
      done();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setSaving(false); }
  }

  const setTable = (index: number, table: DraftTable) =>
    edit({
      ...draft,
      tables: draft.tables.map((old, i) => (i === index ? table : old)),
    });

  const issueCount = draft.issues.length;

  return (
    <section>
      <h1 className="title">Conferir {monthLabel(month)}</h1>
      <p className="note">
        Confira os participantes, os valores e os bônus antes de abrir o resultado.
        Duração usa minutos; distância usa quilômetros.
      </p>

      {draft.run && <p className="note">Período mensal: {month}-01 até {draft.annual_end_date}.<br />
        Corte anual: 2026-01-01 até {draft.annual_end_date}. Revisão {draft.revision}.</p>}
      {!!draft.differences?.length && <details className="panel" open>
        <summary>{draft.differences.length} diferenças contra a apuração anterior</summary>
        <ul>{draft.differences.map((diff, i) => <li key={i}>
          {diff.name} · {metricLabel(diff.metric)} ({periodLabel(diff.period)}): {diff.previous ?? "ausente"} → {diff.collected ?? "ausente"}
        </li>)}</ul>
      </details>}
      <details className="panel"><summary>Participantes e bônus de calorias (+20%)</summary>
        {participants.map(person => <label className="bonus-choice" key={person.name}>
          <input type="checkbox" checked={person.calorie_bonus} disabled={saving}
            onChange={event => {
              setSaving(true);
              api.bonus(person.name, event.target.checked).then(people => {
                setParticipants(people); save(draft);
              }, reason => { setSaving(false); setError(String(reason)); });
            }} /> {person.name}
        </label>)}
      </details>
      <datalist id="roster">
        {participants.map((person) => (
          <option key={person.name} value={person.name} />
        ))}
      </datalist>

      <p className={issueCount > 0 ? "legend legend--warn" : "legend"}>
        {issueCount > 0
          ? `${issueCount} ${plural(issueCount, "linha destacada", "linhas destacadas")} — revise antes de continuar.`
          : "Nada destacado."}{" "}
        {saving && <span className="dim">salvando…</span>}
      </p>

      {error && (
        <div className="panel panel--warn" role="alert">
          <p>{error}</p>
        </div>
      )}

      {draft.tables.map((table, index) => (
        <TableCard
          key={index}
          batch={batch}
          table={table}
          issues={draft.issues.filter((issue) => issue.table === index)}
          participants={participants}
          onChange={(updated) => setTable(index, updated)}
          onRemove={() =>
            edit({ ...draft, tables: draft.tables.filter((_, i) => i !== index) })
          }
          onRoster={(people) => {
            setParticipants(people);
            // The roster changed, so the verdict on every unknown name has to
            // be recomputed. Resending the draft is what does that.
            save(draft);
          }}
        />
      ))}

      <div className="actions">
        <button
          type="button"
          className="button button--ghost"
          onClick={() => edit({ ...draft, tables: [...draft.tables, BLANK_TABLE] })}
        >
          + tabela
        </button>
        <button type="button" className="button button--ghost" disabled={saving} onClick={() => void leave(onBack)}>
          Voltar
        </button>
        <button type="button" className="button" disabled={saving || !!error} onClick={() => void leave(onDone)}>
          Ver o resultado
        </button>
      </div>
    </section>
  );
}
