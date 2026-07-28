import { useEffect, useState } from "react";

/**
 * Hash routing, in one file and no dependency.
 *
 * GitHub Pages serves static files: a real path like /gymrats/mes/2026-06
 * would 404 on reload unless the deploy carried a fallback. Everything after
 * the "#" never reaches the server, so a link to a month survives being
 * shared, bookmarked and reloaded.
 */
export type Route =
  | { view: "month"; month: string | null }
  | { view: "season"; year: number | null }
  | { view: "admin" };

const MONTH_PATTERN = /^\d{4}-\d{2}$/;
const YEAR_PATTERN = /^\d{4}$/;

/** `null` in a route means "whatever is the most recent" -- resolved by App. */
export function parseRoute(hash: string): Route {
  const [head, tail] = hash.replace(/^#\/?/, "").split("/");

  if (head === "mes") {
    return { view: "month", month: tail && MONTH_PATTERN.test(tail) ? tail : null };
  }
  if (head === "ano") {
    return { view: "season", year: tail && YEAR_PATTERN.test(tail) ? Number(tail) : null };
  }
  // The admin area only exists in the local build; in the static one the
  // route falls through to the month view because there is nothing to show.
  if (head === "admin" && __LOCAL__) {
    return { view: "admin" };
  }
  return { view: "month", month: null };
}

export function routeHref(route: Route): string {
  switch (route.view) {
    case "month":
      return route.month ? `#/mes/${route.month}` : "#/";
    case "season":
      return route.year ? `#/ano/${route.year}` : "#/ano";
    case "admin":
      return "#/admin";
  }
}

export function useRoute(): Route {
  const [hash, setHash] = useState(() => window.location.hash);

  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  useEffect(() => {
    // A month picked at the bottom of a long table should not leave the reader
    // halfway down the next one.
    window.scrollTo({ top: 0 });
  }, [hash]);

  return parseRoute(hash);
}
