import { DataError } from "../data/source";

export function Loading({ what }: { what: string }) {
  return (
    <p className="status" role="status">
      Carregando {what}…
    </p>
  );
}

export function Failure({ error }: { error: Error }) {
  return (
    <div className="status status--error" role="alert">
      <p>{error.message}</p>
      {error instanceof DataError && <p className="status__url">{error.url}</p>}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="status">{children}</p>;
}
