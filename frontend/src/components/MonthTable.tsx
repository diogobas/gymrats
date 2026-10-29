import { formatDecimal, formatDuration, formatInteger, formatKm } from "../format";
import { SCORING_MODALITIES, type MonthStanding, type ScoringModality } from "../types";
import { TiebreakBadge, TiebreakNote } from "./Tiebreaks";

const HEADING: Record<ScoringModality, { short: string; long: string }> = {
  hustle: { short: "H", long: "hustle points" },
  active_days: { short: "D", long: "dias ativos" },
  calories: { short: "C", long: "calorias" },
  duration: { short: "T", long: "duração" },
};

function Value({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="value">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Detail({ row }: { row: MonthStanding }) {
  const { values } = row;
  return (
    <div className="detail">
      <dl className="values">
        <Value label={row.positions.hustle === null ? "Hustle · desconsiderado" : `Hustle · ${row.positions.hustle}º`}>
          {formatDecimal(values.hustle)} pts
        </Value>
        <Value label={`Dias ativos · ${row.positions.active_days}º`}>
          {formatInteger(values.active_days)}
        </Value>
        <Value label={`Calorias · ${row.positions.calories}º`}>
          <span className="nowrap">{formatInteger(values.calories.raw)} kcal</span>
          {values.calories.bonus_applied && (
            // The bonus moved six of June's ten places. Showing only the
            // adjusted figure would make the site disagree with the app;
            // showing only the raw one would make the order look wrong.
            <span className="bonus">+20% → {formatInteger(values.calories.adjusted)}</span>
          )}
        </Value>
      </dl>
      <dl className="values values--muted">
        <Value label="Distância">{formatKm(values.distance_km)}</Value>
        <Value label={row.positions.duration != null ? `Duração · ${row.positions.duration}º` : "Duração"}>{formatDuration(values.duration_label)}</Value>
      </dl>
      <p className="hint">{row.positions.duration != null
        ? "A duração pontua neste mês. A ordem dos empates segue a classificação oficial."
        : "Distância e duração não pontuam — só desempatam."}</p>
      <TiebreakNote tiebreak={row.tiebreak} />
    </div>
  );
}

export function MonthTable({
  standings,
  open,
  onToggle,
}: {
  standings: readonly MonthStanding[];
  /** Whose row is expanded. Held by the parent so the tiebreak summary below
   * the table can skip whatever is already spelled out on screen. */
  open: string | null;
  onToggle: (name: string | null) => void;
}) {
  const modalities: readonly ScoringModality[] = standings.some(row => row.positions.duration != null)
    ? ["hustle", "active_days", "duration", "calories"]
    : SCORING_MODALITIES;
  return (
    <ol className={`standings${modalities.length === 4 ? " standings--four" : ""}`}>
      <li className="standings__head" aria-hidden="true">
        <span className="cell cell--pos">#</span>
        <span className="cell cell--name">nome</span>
        {modalities.map((modality) => (
          <span key={modality} className="cell cell--part" title={HEADING[modality].long}>
            {HEADING[modality].short}
          </span>
        ))}
        <span className="cell cell--total">pts</span>
      </li>

      {standings.map((row) => {
        const expanded = open === row.name;
        return (
          <li key={row.name} className={expanded ? "is-open" : undefined}>
            <button
              type="button"
              className="row"
              aria-expanded={expanded}
              onClick={() => onToggle(expanded ? null : row.name)}
            >
              <span className="cell cell--pos">{row.position}</span>
              <span className="cell cell--name">
                {row.name}
                <TiebreakBadge tiebreak={row.tiebreak} />
              </span>
              {modalities.map((modality) => (
                <span key={modality} className="cell cell--part">
                  {row.positions[modality] ?? "—"}
                </span>
              ))}
              <span className="cell cell--total">{row.total}</span>
              <span className="chevron" aria-hidden="true" />
            </button>
            {expanded && <Detail row={row} />}
          </li>
        );
      })}
    </ol>
  );
}
