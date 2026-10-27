import type { Draft } from "./types";

/** One writer per review screen. Old responses never overwrite newer edits. */
export class DraftSaver {
  private tail: Promise<Draft>;
  constructor(initial: Draft, private write: (draft: Draft) => Promise<Draft>) {
    this.tail = Promise.resolve(initial);
  }
  save(draft: Draft): Promise<Draft> {
    this.tail = this.tail.then(previous => this.write({ ...draft, revision: previous.revision }));
    return this.tail;
  }
  flush(): Promise<Draft> { return this.tail; }
}
