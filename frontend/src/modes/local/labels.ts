export function metricLabel(metric: string): string {
  return ({ hustle: "Hustle", active_days: "Dias ativos", calories: "Calorias (kcal)",
    distance: "Distância (km)", duration: "Duração (min)" } as Record<string, string>)[metric] ?? metric;
}
export function periodLabel(period: string): string {
  return period === "year" ? "Ano até o mês" : "Mês";
}
