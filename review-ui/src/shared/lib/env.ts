/**
 * Runtime environment.
 *
 * In dev the Vite proxy forwards `/api` to the FastAPI backend, so the
 * default empty base means "same origin". Override via `VITE_API_BASE_URL`
 * for production deployments.
 */
export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, ""),
} as const;
