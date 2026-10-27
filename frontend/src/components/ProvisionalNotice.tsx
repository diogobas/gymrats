/** A saved snapshot of an unfinished month, shared by public and admin views. */
export function ProvisionalNotice({ info, season = false }: {
  info: { provisional?: boolean; data_through?: string; pending_review?: boolean };
  season?: boolean;
}) {
  if (!info.provisional) return null;
  const cutoff = info.data_through?.split("-").reverse().join("/");
  return <p className="note provisional-notice" role="status">
    <strong>{season ? "Acumulado provisório" : info.pending_review ? "Aguardando fechamento" : "Mês em andamento"}</strong>
    {cutoff && ` · dados até ${cutoff}.`} {info.pending_review ? "Mês encerrado, aguardando conferência e fechamento definitivo." : "As posições podem mudar até o fechamento."}
  </p>;
}
