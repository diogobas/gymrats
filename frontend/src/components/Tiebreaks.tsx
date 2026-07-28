import type { Tiebreak } from "../types";
import { joinNames, plural } from "../format";

/**
 * Why someone is above someone else on the same score.
 *
 * The sentence is not assembled here. `storage/schema.py` renders it and it
 * travels in the JSON, so what the site shows is exactly what the tally
 * decided -- which is the whole point of publishing it: nobody has to take the
 * admin's word for the order in the group chat.
 */

export function TiebreakBadge({ tiebreak }: { tiebreak: Tiebreak | null }) {
  if (!tiebreak) return null;
  const unresolved = tiebreak.resolved_by === null;
  return (
    <span
      className={`badge${unresolved ? " badge--warn" : ""}`}
      title={tiebreak.detail}
      aria-label={unresolved ? "empate não resolvido" : "posição definida por desempate"}
    >
      {unresolved ? "=" : "≠"}
    </span>
  );
}

export function TiebreakNote({ tiebreak }: { tiebreak: Tiebreak | null }) {
  if (!tiebreak) return null;
  return (
    <p className={`tiebreak${tiebreak.resolved_by === null ? " tiebreak--warn" : ""}`}>
      {tiebreak.detail}
    </p>
  );
}

type Tied = { name: string; tiebreak: Tiebreak };

/**
 * Every tie, listed once, without having to open anything.
 *
 * One entry per tie and not one per person: everybody in a tied group carries
 * the same explanation. `expanded` is whoever the reader has open right now --
 * their tie is already spelled out on screen, so repeating it here would print
 * the same sentence twice.
 */
export function TiebreakSummary({
  rows,
  expanded,
}: {
  rows: readonly Tied[];
  expanded?: string | null;
}) {
  const seen = new Set<string>();
  const groups: Tied[] = [];

  for (const row of rows) {
    const names = [row.name, ...row.tiebreak.tied_with];
    if (expanded && names.includes(expanded)) continue;
    const key = [...names].sort().join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    groups.push(row);
  }

  if (groups.length === 0) return null;

  return (
    <section className="panel">
      <h2 className="panel__title">
        {plural(groups.length, "Desempate aplicado", "Desempates aplicados")}
      </h2>
      <ul className="panel__list">
        {groups.map((row) => (
          <li key={row.name}>
            <strong>{joinNames([row.name, ...row.tiebreak.tied_with])}</strong>
            <TiebreakNote tiebreak={row.tiebreak} />
          </li>
        ))}
      </ul>
    </section>
  );
}

export function UnresolvedTies({ groups }: { groups: readonly string[][] }) {
  if (groups.length === 0) return null;
  return (
    <section className="panel panel--warn">
      <h2 className="panel__title">Empate sem critério</h2>
      <p>
        A cascata de desempate — distância, depois duração — não separou{" "}
        {groups.map((group) => joinNames(group)).join("; ")}. As posições estão
        divididas até a decisão do admin.
      </p>
    </section>
  );
}
