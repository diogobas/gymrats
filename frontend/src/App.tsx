import { Suspense, lazy } from "react";
import { MonthView } from "./components/MonthView";
import { SeasonView } from "./components/SeasonView";
import { Empty, Failure, Loading } from "./components/Status";
import { YearPicker } from "./components/YearPicker";
import { source } from "./data/current";
import { formatTimestamp } from "./format";
import { monthHref, selectedYear } from "./navigation";
import { useRoute, type Route } from "./router";
import type { IndexDocument } from "./types";
import { useAsync } from "./useAsync";

/**
 * The admin half of the app, and the only thing the two builds disagree about.
 *
 * `__LOCAL__` is substituted by a literal at build time, so in the static build
 * this is `false ? ... : null` -- Rollup folds it, drops the arrow function,
 * and never emits the chunk it would have imported. The upload screen is
 * absent from the static bundle, not hidden in it; `tests/bundle.test.ts`
 * checks the built files to keep that honest.
 */
const loadAdmin = __LOCAL__ ? () => import("./modes/local/AdminApp") : null;
const AdminApp = loadAdmin ? lazy(loadAdmin) : null;

function Tabs({ route, index }: { route: Route; index?: IndexDocument }) {
  const view = route.view;
  const selected = index ? selectedYear(index, route) : null;
  const year = index && selected !== null && index.years.includes(selected)
    ? selected : index?.latest_year ?? null;
  return (
    <nav className="tabs" aria-label="Seções">
      <a href={index ? monthHref(index, year) : "#/"} className={view === "month" ? "is-current" : undefined}>
        Mês
      </a>
      <a href={year === null ? "#/ano" : `#/ano/${year}`} className={view === "season" ? "is-current" : undefined}>
        Ano
      </a>
      {AdminApp && (
        <a href="#/admin" className={view === "admin" ? "is-current" : undefined}>
          Apurar
        </a>
      )}
    </nav>
  );
}

function Content({ index, route }: { index: IndexDocument; route: Route }) {
  if (route.view === "admin") {
    // parseRoute never returns this in the static build; TypeScript does not
    // know that, and a fallback costs one line.
    return AdminApp ? (
      <Suspense fallback={<Loading what="a apuração" />}>
        <AdminApp />
      </Suspense>
    ) : (
      <Empty>Essa tela só existe na versão local.</Empty>
    );
  }
  if (index.years.length === 0) return <Empty>Nenhum resultado publicado.</Empty>;
  const year = selectedYear(index, route);
  const available = year !== null && index.years.includes(year);
  const month = route.view === "month" ? route.month ?? index.latest_month ?? "" : "";
  return (
    <>
      <YearPicker index={index} year={year} view={route.view} />
      {!available ? <Empty>Esse ano não tem resultados publicados. Escolha outro ano.</Empty>
        : route.view === "season" ? <SeasonView key={year} year={year} />
        : <MonthView key={month} index={index} month={month} />}
    </>
  );
}

export function App() {
  const route = useRoute();
  const index = useAsync(() => source.index(), []);

  return (
    <div className="app">
      <header className="header">
        <span className="header__brand">
          <img
            className="header__logo"
            src={`${import.meta.env.BASE_URL}apple-touch-icon.png`}
            alt=""
            width={32}
            height={32}
          />
          GymRats
        </span>
        <Tabs route={route} index={index.status === "ready" ? index.value : undefined} />
      </header>

      <main>
        {index.status === "loading" && <Loading what="a temporada" />}
        {index.status === "error" && <Failure error={index.error} />}
        {index.status === "ready" && <Content index={index.value} route={route} />}
      </main>

      <footer className="footer">
        {index.status === "ready" && (
          <p>Apurado em {formatTimestamp(index.value.generated_at)}</p>
        )}
        <p>
          Distância e duração não pontuam: entram só no desempate, nessa ordem.
          Calorias com o bônus de +20% são marcadas na linha.
        </p>
      </footer>
    </div>
  );
}
