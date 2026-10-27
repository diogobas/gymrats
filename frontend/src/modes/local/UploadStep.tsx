import { useEffect, useState } from "react";
import { monthLabel } from "../../format";
import { api } from "./api";
import type { Health, ScreenshotItem } from "./types";

/**
 * Step one: get the screenshots onto the laptop.
 *
 * `accept="image/*"` plus `multiple` is what makes iOS open the camera roll
 * with multi-select instead of the file browser -- ten screenshots in one
 * gesture, which is the whole month's input.
 */

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** The month being tallied is almost always the one that just ended. */
function previousMonth(): string {
  const now = new Date();
  now.setDate(1);
  now.setMonth(now.getMonth() - 1);
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function UploadStep({
  month,
  onMonth,
  onBatch,
}: {
  month: string;
  onMonth: (month: string) => void;
  onBatch: (batch: string) => void;
}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [picked, setPicked] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [pending, setPending] = useState<
    { batch_id: string; items: ScreenshotItem[] }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth, (reason: Error) => setError(reason.message));
    // Anything still in the inbox is a review that was started and not
    // finished -- the draft is saved next to those screenshots, so picking the
    // batch up again is the whole point of it having been saved.
    api.scan().then((response) => setPending(response.batches), () => undefined);
  }, []);

  useEffect(() => {
    const urls = picked.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach(URL.revokeObjectURL);
  }, [picked]);

  async function run<T>(work: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await work();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  const send = () =>
    run(async () => {
      const response = await api.upload(picked);
      onBatch(response.batch_id);
    });

  const scan = () =>
    run(async () => {
      const response = await api.scan();
      setPending(response.batches);
      if (response.batches.length === 0) {
        setError("Nenhum print pendente na fonte configurada.");
      }
    });

  return (
    <section>
      <h1 className="title">Apurar um mês</h1>

      <label className="field">
        <span>Mês</span>
        <input
          type="month"
          min="2026-01"
          max={previousMonth() < "2026-12" ? previousMonth() : "2026-12"}
          value={month}
          onChange={(event) => onMonth(event.target.value || previousMonth())}
        />
      </label>
      <p className="hint">{monthLabel(month)}</p>

      {health && (
        <p className="legend">
          fonte: <strong>{health.source}</strong> · OCR:{" "}
          <strong>{health.ocr_engine}</strong>
          {health.ocr_engine === "manual" &&
            " — nenhum print será lido automaticamente; você digita os valores na conferência."}
        </p>
      )}

      {health?.source === "upload" ? (
        <>
          <label className="upload">
            <input
              type="file"
              name="files[]"
              accept="image/*"
              multiple
              onChange={(event) => setPicked(Array.from(event.target.files ?? []))}
            />
            <span>Escolher prints do rolo da câmera</span>
          </label>

          {picked.length > 0 && (
            <>
              <ul className="previews">
                {picked.map((file, index) => (
                  <li key={file.name + index}>
                    <img src={previews[index]} alt={file.name} />
                    <span>{file.name}</span>
                  </li>
                ))}
              </ul>
              <button className="button" type="button" disabled={busy} onClick={send}>
                {busy ? "Enviando…" : `Enviar ${picked.length} print(s)`}
              </button>
            </>
          )}
        </>
      ) : (
        <>
          <p className="note">
            A fonte ativa não recebe upload. Procure os prints onde ela olha.
          </p>
          <button className="button" type="button" disabled={busy} onClick={scan}>
            {busy ? "Procurando…" : "Procurar prints"}
          </button>
        </>
      )}

      {pending.length > 0 && (
        <section className="panel">
          <h2 className="panel__title">Lotes pendentes</h2>
          <p className="hint">
            Prints que ainda não viraram um mês fechado. As correções que você já
            tinha feito continuam salvas.
          </p>
          <ul className="panel__list">
            {pending.map((item) => (
              <li key={item.batch_id} className="pending">
                <span>
                  <strong>{item.batch_id}</strong>
                  <br />
                  <span className="dim">{item.items.length} print(s)</span>
                </span>
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => onBatch(item.batch_id)}
                >
                  Retomar
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {error && (
        <div className="panel panel--warn" role="alert">
          <p>{error}</p>
        </div>
      )}
    </section>
  );
}

export { currentMonth, previousMonth };
