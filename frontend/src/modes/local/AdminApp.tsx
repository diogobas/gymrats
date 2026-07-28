import { useState } from "react";

/**
 * The admin half: upload the month's screenshots, review what OCR read, tally.
 *
 * Only reachable in the local build. Everything under `modes/local/` is
 * compiled out of the static site -- see App.tsx and tests/bundle.test.ts.
 *
 * Step 2 ships the picker and the previews. Sending them to FastAPI, and the
 * review screen where every extracted value can be corrected, is step 3.
 */

/** Grep target for the bundle test. Renaming it means renaming it there too. */
export const UPLOAD_MARKER = "gymrats-admin-upload";

interface Picked {
  file: File;
  url: string;
}

export default function AdminApp() {
  const [picked, setPicked] = useState<Picked[]>([]);

  function choose(files: FileList | null) {
    for (const item of picked) URL.revokeObjectURL(item.url);
    setPicked(
      Array.from(files ?? []).map((file) => ({
        file,
        url: URL.createObjectURL(file),
      })),
    );
  }

  return (
    <section data-testid={UPLOAD_MARKER}>
      <h1 className="title">Apurar o mês</h1>
      <p className="note">
        Selecione os prints das classificações direto do rolo da câmera. O envio
        para a API e a tela de conferência entram no passo 3.
      </p>

      <label className="upload">
        <input
          type="file"
          name="files[]"
          accept="image/*"
          multiple
          onChange={(event) => choose(event.target.files)}
        />
        <span>Escolher prints</span>
      </label>

      {picked.length > 0 && (
        <>
          <p className="legend">
            {picked.length} print(s) selecionado(s) — nada foi enviado ainda.
          </p>
          <ul className="previews">
            {picked.map((item) => (
              <li key={item.file.name}>
                <img src={item.url} alt={item.file.name} />
                <span>{item.file.name}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
