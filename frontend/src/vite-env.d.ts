/// <reference types="vite/client" />

/** True only in the admin build. Substituted at build time by vite.config.ts. */
declare const __LOCAL__: boolean;

/** "static" or "local". For display; branch on __LOCAL__, never on this. */
declare const __APP_MODE__: string;
