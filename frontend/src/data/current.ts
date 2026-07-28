import type { DataSource } from "./source";
import { staticSource } from "./staticSource";

/**
 * The source the read-only screens use.
 *
 * Both builds read the published JSON today. When the API lands, the local
 * build points this at FastAPI and nothing above it changes.
 */
export const source: DataSource = staticSource;
