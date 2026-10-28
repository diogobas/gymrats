import { Suspense, lazy } from "react";
import { MonthView } from "./components/MonthView";
import { SeasonView } from "./components/SeasonView";
import { Empty, Failure, Loading } from "./components/Status";
import { source } from "./data/current";
import { formatTimestamp } from "./format";
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

function Tabs({ view }: { view: string }) {
  return (
    <nav className="tabs" aria-label="Seções">
      <a href="#/" className={view === "month" ? "is-current" : undefined}>
        Mês
      </a>
      <a href="#/ano" className={view === "season" ? "is-current" : undefined}>
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
  if (route.view === "season") {
    return <SeasonView year={route.year ?? index.latest_year ?? 0} />;
  }
  return <MonthView index={index} month={route.month ?? index.latest_month ?? ""} />;
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
        <Tabs view={route.view} />
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
