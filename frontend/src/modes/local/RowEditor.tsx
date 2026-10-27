import { useState } from "react";
import { api } from "./api";
import type { DraftRow, Issue, Participant } from "./types";

/**
 * One line of one leaderboard: what the app printed, and who it is.
 *
 * Three fields, side by side on a phone: the rank down the right-hand side of
 * the screenshot, the name, and the value exactly as written ("14,939
 * calorias"). The value is not a number input on purpose -- the string is what
 * the domain parses, and retyping "14939" would quietly drop the check that
 * the string was read correctly.
 */

function UnknownName({
  row,
  participants,
  onLink,
  onRegister,
}: {
  row: DraftRow;
  participants: Participant[];
  onLink: (canonical: string) => void;
  onRegister: () => void;
}) {
  const [choice, setChoice] = useState("");

  return (
    <div className="fix">
      <p className="hint">
        “{row.name}” não está no cadastro. Vincular ensina o apelido de vez — no
        mês que vem esse mesmo print se resolve sozinho.
      </p>
      <div className="fix__actions">
        <select value={choice} onChange={(event) => setChoice(event.target.value)}>
          <option value="">é quem?</option>
          {participants.map((person) => (
            <option key={person.name} value={person.name}>
              {person.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="button button--small"
          disabled={!choice}
          onClick={() => onLink(choice)}
        >
          Vincular
        </button>
        <button type="button" className="button button--small" onClick={onRegister}>
          Cadastrar
        </button>
      </div>
    </div>
  );
}

export function RowEditor({
  row,
  issues,
  participants,
  onChange,
  onRemove,
  onRoster,
}: {
  row: DraftRow;
  issues: Issue[];
  participants: Participant[];
  onChange: (row: DraftRow) => void;
  onRemove: () => void;
  onRoster: (participants: Participant[]) => void;
}) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unknown = issues.some((issue) => issue.type === "unknown_name");

  async function link(canonical: string) {
    setWorking(true);
    setError(null);
    try {
      const person = participants.find((item) => item.name === canonical);
      const aliases = [...(person?.aliases ?? []), row.name];
      onRoster(await api.addAlias(canonical, aliases));
      // The row keeps the name the screenshot showed; the roster now knows it.
      onChange({ ...row });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function register() {
    setWorking(true);
    setError(null);
    try {
      onRoster(await api.createParticipant({ name: row.name }));
      onChange({ ...row });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <li className={issues.length > 0 ? "editor is-flagged" : "editor"}>
      <div className="editor__fields">
        <input
          className="editor__position"
          type="number"
          inputMode="numeric"
          aria-label="posição no print"
          placeholder="#"
          value={row.position ?? ""}
          onChange={(event) =>
            onChange({
              ...row,
              position: event.target.value === "" ? null : Number(event.target.value),
            })
          }
        />
        <input
          className="editor__name"
          aria-label="nome"
          placeholder="nome"
          list="roster"
          value={row.name}
          onChange={(event) => onChange({ ...row, name: event.target.value })}
        />
        <input
          className="editor__value"
          aria-label="valor como está no print"
          placeholder="ex.: 14,939 calorias"
          value={row.raw_value}
          onChange={(event) => onChange({ ...row, raw_value: event.target.value })}
        />
        <button
          type="button"
          className="editor__remove"
          aria-label={`remover ${row.name || "linha"}`}
          onClick={onRemove}
        >
          ×
        </button>
      </div>

      {row.resolved_name && row.resolved_name !== row.name && (
        <p className="hint">= {row.resolved_name}</p>
      )}

      {issues.map((issue, index) => (
        <p className="tiebreak tiebreak--warn" key={index}>
          {issue.message}
        </p>
      ))}

      {error && <p role="alert" className="tiebreak tiebreak--warn">{error}</p>}
      {unknown && row.name.trim() !== "" && !working && (
        <UnknownName
          row={row}
          participants={participants}
          onLink={link}
          onRegister={register}
        />
      )}
    </li>
  );
}
