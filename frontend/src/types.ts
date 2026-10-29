/**
 * The published JSON, as TypeScript.
 *
 * Written by `backend/gymrats/storage/schema.py` and `publisher.py`. Nothing
 * here is computed on the client: the site renders what it is given, including
 * the sentence that explains a tiebreak.
 */

/** The three leaderboards that add up to the monthly score. */
export const SCORING_MODALITIES = ["hustle", "active_days", "calories"] as const;

export type ScoringModality = (typeof SCORING_MODALITIES)[number] | "duration";

export interface CalorieValue {
  /** What the app showed, before any bonus. */
  raw: number | null;
  bonus_applied: boolean;
  /** What the ranking used, including the historical bonus when applicable. */
  adjusted: number | null;
}

export interface Tiebreak {
  tied_with: string[];
  /** "distance", "duration", or null when the cascade ran out of criteria. */
  resolved_by: string | null;
  comparison: Record<string, number>;
  /** Ready to print, in Portuguese. Rendered by the backend. */
  detail: string;
}

export interface MonthValues {
  hustle: number | null;
  active_days: number | null;
  calories: CalorieValue;
  distance_km: number | null;
  duration_min: number | null;
  duration_label: string | null;
}

export interface MonthStanding {
  position: number;
  name: string;
  total: number;
  positions: Record<(typeof SCORING_MODALITIES)[number], number | null> & { duration?: number | null };
  values: MonthValues;
  tiebreak: Tiebreak | null;
}

export interface Exclusion {
  name: string;
  reason: string;
}

export interface MonthDocument extends SnapshotInfo {
  official_source?: string;
  ignore_hustle?: boolean;
  schema_version: number;
  month: string;
  generated_at: string;
  ranked_count: number;
  standings: MonthStanding[];
  excluded: Exclusion[];
  unresolved_ties: string[][];
}

export interface SeasonStanding {
  position: number;
  name: string;
  total: number;
  by_month: Record<string, number>;
  /** Months with absence scores, including explicit historical exceptions. */
  imputed_months: string[];
  tiebreak: Tiebreak | null;
}

export interface SeasonDocument extends SnapshotInfo {
  official_source?: string;
  absence_overrides?: Record<string, number>;
  missing_months?: string[];
  schema_version: number;
  year: number;
  generated_at: string;
  months: string[];
  standings: SeasonStanding[];
  unresolved_ties: string[][];
}

export interface IndexMonth extends SnapshotInfo {
  month: string;
  year: number;
  /**
   * False for the months tallied by hand before this system: no leaderboards
   * survive, so there is no month document -- only the finishing order, which
   * lives in the season columns.
   */
  detail: boolean;
}

export interface IndexDocument {
  schema_version: number;
  generated_at: string;
  latest_month: string | null;
  latest_completed_month?: string | null;
  latest_year: number | null;
  years: number[];
  months: IndexMonth[];
}

export interface SnapshotInfo {
  pending_review?: boolean;
  provisional?: boolean;
  data_through?: string;
}
