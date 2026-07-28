import { useState } from "react";
import { api } from "./api";
import { PreviewStep } from "./PreviewStep";
import { ReviewStep } from "./ReviewStep";
import { UploadStep, previousMonth } from "./UploadStep";
import type { Draft } from "./types";

/**
 * The admin half: upload the screenshots, review what came out, close the month.
 *
 * Only reachable in the local build. Everything under `modes/local/` is
 * compiled out of the static site -- see App.tsx and tests/bundle.test.ts.
 *
 * Three steps, and the middle one is not skippable. Not because the API would
 * refuse a commit -- it never does -- but because the whole point of the
 * exercise is that somebody looked.
 */

/** Grep target for the bundle test. Renaming it means renaming it there too. */
export const UPLOAD_MARKER = "gymrats-admin-upload";

type Step = "upload" | "review" | "preview";

const STEP_LABELS: Record<Step, string> = {
  upload: "Prints",
  review: "Conferir",
  preview: "Fechar",
};

export default function AdminApp() {
  const [step, setStep] = useState<Step>("upload");
  const [month, setMonth] = useState(previousMonth);
  const [batch, setBatch] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function readBatch(id: string) {
    setBatch(id);
    setError(null);
    try {
      // A draft already saved for this batch wins: it has the corrections.
      const existing = await api.loadDraft(id).catch(() => null);
      const next = existing ?? (await api.read(id, month));
      // Resuming means resuming the month that draft was for, not whatever
      // the picker happens to be showing.
      if (next.month) setMonth(next.month);
      setDraft(next);
      setStep("review");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <div data-testid={UPLOAD_MARKER}>
      <ol className="steps" aria-label="etapas">
        {(Object.keys(STEP_LABELS) as Step[]).map((name, index) => (
          <li key={name} className={step === name ? "is-current" : undefined}>
            {index + 1}. {STEP_LABELS[name]}
          </li>
        ))}
      </ol>

      {error && (
        <div className="panel panel--warn" role="alert">
          <p>{error}</p>
        </div>
      )}

      {step === "upload" && (
        <UploadStep month={month} onMonth={setMonth} onBatch={readBatch} />
      )}

      {step === "review" && batch && draft && (
        <ReviewStep
          batch={batch}
          month={month}
          draft={draft}
          onDraft={setDraft}
          onDone={() => setStep("preview")}
          onBack={() => setStep("upload")}
        />
      )}

      {step === "preview" && batch && draft && (
        <PreviewStep
          batch={batch}
          month={month}
          draft={draft}
          onBack={() => setStep("review")}
        />
      )}
    </div>
  );
}
