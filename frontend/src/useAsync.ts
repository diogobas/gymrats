import { useEffect, useState } from "react";

export type Async<T> =
  | { status: "loading" }
  | { status: "ready"; value: T }
  | { status: "error"; error: Error };

/**
 * Run a promise and describe where it got to.
 *
 * Deliberately tiny: the site loads three JSON files and nothing else. A stale
 * response is discarded rather than rendered, which is what stops a slow month
 * from overwriting the one the reader has already switched to.
 */
export function useAsync<T>(load: () => Promise<T>, deps: readonly unknown[]): Async<T> {
  const [state, setState] = useState<Async<T>>({ status: "loading" });

  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    load().then(
      (value) => current && setState({ status: "ready", value }),
      (error: unknown) =>
        current &&
        setState({
          status: "error",
          error: error instanceof Error ? error : new Error(String(error)),
        }),
    );
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
