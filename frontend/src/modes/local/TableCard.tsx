import { useState } from "react";
import { api } from "./api";
import { RowEditor } from "./RowEditor";
import type { DraftRow, DraftTable, Issue, Participant } from "./types";

/**
 * One leaderboard, beside the screenshot it came from.
 *
 * On a phone there is no room for a real side-by-side, so the image sits on
 * top, tall enough to read and tappable to fill the screen, with the rows
 * under it. Which is the order you work in anyway: look, then type.
 */

const MODALITIES = [
  ["hustle", "hustle points"],
  ["active_days", "dias ativos"],
  ["calories", "calorias"],
  ["distance", "distância"],
  ["duration", "duração"],
] as const;

const PERIODS = [
  ["month", "Este mês"],
  ["year", "Este ano"],
] as const;

const EMPTY_ROW: DraftRow = {
  name: "",
  raw_value: "",
  position: null,
  resolved_name: null,
  value: null,
};

export function TableCard({
  batch,
  table,
  issues,
  participants,
  onChange,
  onRemove,
  onRoster,
}: {
  batch: string;
  table: DraftTable;
  issues: Issue[];
  participants: Participant[];
  onChange: (table: DraftTable) => void;
  onRemove: () => void;
  onRoster: (participants: Participant[]) => void;
}) {
  const [zoomed, setZoomed] = useState<string | null>(null);

  const tableIssues = issues.filter((issue) => issue.row === null);
  const rowIssues = (index: number) => issues.filter((issue) => issue.row === index);

  function setRow(index: number, row: DraftRow) {
    onChange({ ...table, rows: table.rows.map((old, i) => (i === index ? row : old)) });
  }

  return (
    <section className={`card${issues.length > 0 ? " is-flagged" : ""}`}>
      <header className="card__head">
        <h2 className="panel__title">{table.label}</h2>
        <button
          type="button"
          className="editor__remove"
          aria-label="descartar essa tabela"
          onClick={onRemove}
        >
          ×
        </button>
      </header>

      {table.sources.length > 0 && (
        <div className="shots">
          {table.sources.map((item) => (
            <button
              key={item}
              type="button"
              className="shots__item"
              onClick={() => setZoomed(zoomed === item ? null : item)}
              aria-label={`ampliar ${item}`}
            >
              <img
                className={zoomed === item ? "is-zoomed" : undefined}
                src={api.imageUrl(batch, item)}
                alt={item}
                loading="lazy"
              />
            </button>
          ))}
        </div>
      )}

      <div className="card__selects">
        <label className="field">
          <span>modalidade</span>
          <select
            value={table.modality ?? ""}
            onChange={(event) =>
              onChange({ ...table, modality: event.target.value || null })
            }
          >
            <option value="">qual é?</option>
            {MODALITIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>recorte</span>
          <select
            value={table.period ?? ""}
            onChange={(event) =>
              onChange({ ...table, period: event.target.value || null })
            }
          >
            <option value="">qual é?</option>
            {PERIODS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {tableIssues.map((issue, index) => (
        <p className="tiebreak tiebreak--warn" key={index}>
          {issue.message}
        </p>
      ))}

      <ol className="editors">
        {table.rows.map((row, index) => (
          <RowEditor
            key={index}
            row={row}
            issues={rowIssues(index)}
            participants={participants}
            onChange={(updated) => setRow(index, updated)}
            onRemove={() =>
              onChange({ ...table, rows: table.rows.filter((_, i) => i !== index) })
            }
            onRoster={onRoster}
          />
        ))}
      </ol>

      <button
        type="button"
        className="button button--small"
        onClick={() =>
          onChange({
            ...table,
            rows: [
              ...table.rows,
              { ...EMPTY_ROW, position: table.rows.length + 1 },
            ],
          })
        }
      >
        + linha
      </button>
    </section>
  );
}
