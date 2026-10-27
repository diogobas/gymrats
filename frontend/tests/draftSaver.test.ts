import { describe, expect, it } from "vitest";
import { DraftSaver } from "../src/modes/local/DraftSaver";
import type { Draft } from "../src/modes/local/types";

const initial: Draft = { month: "2026-06", tables: [], issues: [], revision: 1 };

describe("serial autosave", () => {
  it("waits for an outstanding save and uses its revision for the next edit", async () => {
    const calls: Draft[] = [];
    let finish!: (value: Draft) => void;
    const saver = new DraftSaver(initial, draft => {
      calls.push(draft);
      return calls.length === 1 ? new Promise(resolve => { finish = resolve; })
        : Promise.resolve({ ...draft, revision: 3 });
    });
    void saver.save(initial);
    void saver.save({ ...initial, month: "2026-07" });
    await Promise.resolve();
    expect(calls).toHaveLength(1);
    let flushed = false;
    const result = saver.flush().then(value => { flushed = true; return value; });
    await Promise.resolve();
    expect(flushed).toBe(false);
    finish({ ...initial, revision: 2 });
    expect((await result).revision).toBe(3);
    expect(calls.map(value => value.revision)).toEqual([1, 2]);
    expect(calls[1]!.month).toBe("2026-07");
  });

  it("blocks navigation and later writes when a save fails", async () => {
    let calls = 0;
    const saver = new DraftSaver(initial, async () => {
      calls++; throw new Error("Revisão desatualizada");
    });
    await expect(saver.save(initial)).rejects.toThrow("desatualizada");
    await expect(saver.save(initial)).rejects.toThrow("desatualizada");
    await expect(saver.flush()).rejects.toThrow("desatualizada");
    expect(calls).toBe(1);
  });
});
