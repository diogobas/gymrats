import { useCallback, useEffect, useRef, useState } from "react";
import { monthLabel, plural } from "../../format";
import { api } from "./api";
import { TableCard } from "./TableCard";
import type { Draft, DraftTable, Participant } from "./types";

/**
 * Step two: the mandatory look.
 *
 * Nothing here blocks anything -- the admin is the final authority -- but the
 * flow does not skip this screen. Every value is editable, every flagged line
 * is highlighted, and every correction goes back to the API, which re-runs the
 * same checks and answers with what is still wrong.
 *
 * Saving is debounced rather than manual: the review is long, it happens on a
 * phone, and a "salvar" button that is easy to forget is the one thing between
 * twenty corrections and a discarded tab.
 */

const SAVE_DELAY_MS = 700;

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
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    api.participants().then(setParticipants, () => undefined);
  }, []);

  const save = useCallback(
    (next: Draft) => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(async () => {
        setSaving(true);
        setError(null);
        try {
          // The answer is authoritative: resolved names, parsed values and
          // the issues that remain all come back recomputed.
          onDraft(await api.saveDraft(batch, next));
        } catch (reason) {
          setError(reason instanceof Error ? reason.message : String(reason));
        } finally {
          setSaving(false);
        }
      }, SAVE_DELAY_MS);
    },
    [batch, onDraft],
  );

  useEffect(() => () => window.clearTimeout(timer.current), []);

  function edit(next: Draft) {
    onDraft(next);
    save(next);
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
        Cada print com o que foi lido dele. Corrija o que estiver errado — o
        valor vai como está escrito no app, com vírgula de milhar e tudo.
      </p>

      <datalist id="roster">
        {participants.map((person) => (
          <option key={person.name} value={person.name} />
        ))}
      </datalist>

      <p className={issueCount > 0 ? "legend legend--warn" : "legend"}>
        {issueCount > 0
          ? `${issueCount} ${plural(issueCount, "linha destacada", "linhas destacadas")} — nenhuma impede fechar o mês.`
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
        <button type="button" className="button button--ghost" onClick={onBack}>
          Voltar
        </button>
        <button type="button" className="button" onClick={onDone}>
          Ver o resultado
        </button>
      </div>
    </section>
  );
}
