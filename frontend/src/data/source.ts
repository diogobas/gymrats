import type { IndexDocument, MonthDocument, SeasonDocument } from "../types";

/**
 * Where the standings come from.
 *
 * The static site fetches JSON shipped with the build. The admin build will
 * fetch the same shapes from FastAPI, so the screens that read them never
 * learn which one they are talking to.
 */
export interface DataSource {
  index(): Promise<IndexDocument>;
  month(month: string, categoryPath?: string): Promise<MonthDocument>;
  season(year: number, categoryPath?: string): Promise<SeasonDocument>;
}

export class DataError extends Error {
  constructor(
    message: string,
    readonly url: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "DataError";
  }
}
