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
  const category = route.view !== "admin" ? index?.categories?.find(item => item.year === year && item.id === route.category) : undefined;
  const suffix = category ? `?categoria=${category.id}` : "";
  const monthLink = category ? `#/mes/${category.months.at(-1)}${suffix}` : index ? monthHref(index, year) : "#/";
  return (
    <nav className="tabs" aria-label="Seções">
      <a href={monthLink} className={view === "month" ? "is-current" : undefined}>
        Mês
      </a>
      <a href={year === null ? "#/ano" : `#/ano/${year}${suffix}`} className={view === "season" ? "is-current" : undefined}>
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
  const categories = index.categories?.filter(item => item.year === year) ?? [];
  const category = categories.find(item => item.id === route.category);
  const categoryIndex = category ? {
    ...index, months: index.months.filter(item => category.months.includes(item.month)),
  } : index;
  const displayedMonth = category && !category.months.includes(month)
    ? category.months.at(-1)! : month;
  const categoryLink = (id?: string) => {
    const selected = categories.find(item => item.id === id);
    const target = selected && !selected.months.includes(month) ? selected.months.at(-1)! : month;
    return (route.view === "season" ? `#/ano/${year}` : `#/mes/${target}`) + (id ? `?categoria=${id}` : "");
  };
  return (
    <>
      <YearPicker index={index} year={year} view={route.view} />
      {categories.length > 0 && (
        <nav className="picker" aria-label="Escolher categoria">
          <a className={`chip${!category ? " is-current" : ""}`} aria-current={!category ? "page" : undefined} href={categoryLink()}>{categories[0]!.default_label}</a>
          {categories.map(item => <a key={item.id} className={`chip${category?.id === item.id ? " is-current" : ""}`} aria-current={category?.id === item.id ? "page" : undefined} href={categoryLink(item.id)}>{item.label}</a>)}
        </nav>
      )}
      {!available ? <Empty>Esse ano não tem resultados publicados. Escolha outro ano.</Empty>
        : route.view === "season" ? <SeasonView key={`${year}-${category?.id}`} year={year} categoryPath={category?.path} />
        : <MonthView key={`${displayedMonth}-${category?.id}`} index={categoryIndex} month={displayedMonth} categoryPath={category?.path} category={category?.id} />}
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
          Menor soma de posições lidera. As modalidades e os bônus considerados aparecem em cada resultado.
        </p>
      </footer>
    </div>
  );
}
