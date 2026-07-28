import type { IndexDocument, MonthDocument, SeasonDocument } from "../types";
import { DataError, type DataSource } from "./source";

/**
 * The files the publisher wrote into `frontend/public/data/`.
 *
 * BASE_URL is what Vite was built with -- "/" locally, "/gymrats/" on Pages --
 * so no path is ever hard-coded to a deployment.
 */
function url(path: string): string {
  return `${import.meta.env.BASE_URL}data/${path}`;
}

async function get<T>(path: string): Promise<T> {
  const target = url(path);
  let response: Response;
  try {
    response = await fetch(target);
  } catch (cause) {
    throw new DataError("Não foi possível carregar os dados.", target, { cause });
  }
  if (!response.ok) {
    throw new DataError(`Arquivo não encontrado (${response.status}).`, target);
  }
  return (await response.json()) as T;
}

export const staticSource: DataSource = {
  index: () => get<IndexDocument>("index.json"),
  month: (month) => get<MonthDocument>(`months/${month}.json`),
  season: (year) => get<SeasonDocument>(`season/${year}.json`),
};
