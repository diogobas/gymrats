/** A saved snapshot of an unfinished month, shared by public and admin views. */
export function ProvisionalNotice({ info, season = false }: {
  info: { provisional?: boolean; data_through?: string };
  season?: boolean;
}) {
  if (!info.provisional) return null;
  const cutoff = info.data_through?.split("-").reverse().join("/");
  return <p className="note provisional-notice" role="status">
    <strong>{season ? "Acumulado provisório" : "Mês em andamento"}</strong>
    {cutoff && ` · dados até ${cutoff}.`} As posições podem mudar até o fechamento.
  </p>;
}
