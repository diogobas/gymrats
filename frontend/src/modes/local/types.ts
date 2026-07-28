/**
 * The admin API, as TypeScript.
 *
 * Only what the local build needs. The read-only screens keep using the
 * published JSON shapes in `src/types.ts`; a preview response reuses them
 * exactly, which is what lets the preview screen be the site.
 */

import type { MonthDocument, SeasonDocument } from "../../types";

export type IssueType =
  | "position_mismatch"
  | "unknown_name"
  | "unparsed_value"
  | "duplicate_name"
  | "missing_modality"
  | "missing_period";

export interface Issue {
  type: IssueType;
  modality: string | null;
  period: string | null;
  /** Which table, by position in the draft: several can lack a header. */
  table: number | null;
  /** Index into that table's rows, when the problem belongs to one row. */
  row: number | null;
  name: string | null;
  expected: number | null;
  reported: number | null;
  raw_value: string | null;
  /** Ready to show, in Portuguese. Rendered by the backend. */
  message: string;
}

export interface DraftRow {
  name: string;
  raw_value: string;
  position: number | null;
  /** Who that is on the roster; null means nobody knows and the screen asks. */
  resolved_name: string | null;
  /** raw_value parsed; null when it could not be. Never a zero. */
  value: number | null;
}

export interface DraftTable {
  key: string;
  label: string;
  modality: string | null;
  period: string | null;
  /** The screenshots this table was built from -- two when the list is long. */
  sources: string[];
  rows: DraftRow[];
}

export interface Draft {
  month: string | null;
  tables: DraftTable[];
  issues: Issue[];
}

export interface ScreenshotItem {
  id: string;
  batch: string;
  filename: string | null;
  size: number;
  received_at: string | null;
  content_type: string | null;
}

export interface UploadResponse {
  batch_id: string;
  items: ScreenshotItem[];
}

export interface ScanResponse {
  source: string;
  batches: { batch_id: string; items: ScreenshotItem[] }[];
}

export interface Health {
  status: string;
  version: string;
  source: string;
  ocr_engine: string;
}

export interface Participant {
  name: string;
  aliases: string[];
  calorie_bonus: boolean;
}

export interface TallyResponse {
  month: MonthDocument;
  season: SeasonDocument;
  issues: Issue[];
  committed: boolean;
  month_path?: string;
  published?: string[];
}
