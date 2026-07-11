/**
 * Runtime-checked environment access. The values come from `NEXT_PUBLIC_*`
 * build-time inlines; we wrap them in a tiny module so the rest of the
 * app has a single import site, can be mocked in tests, and gets a
 * clear error if a required value is missing.
 */
function readEnv(key: string, fallback?: string): string | undefined {
  const v = process.env[key]
  if (v && v.length > 0) return v
  return fallback
}

function readBool(key: string, fallback: boolean): boolean {
  const v = process.env[key]
  if (!v) return fallback
  return ["1", "true", "yes", "on"].includes(v.toLowerCase())
}

export const env = {
  /** Base URL of the FastAPI backend, e.g. http://localhost:8000. No trailing slash. */
  apiUrl: readEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000")!,
  /**
   * When true, the app shows a persistent "demo restaurant" banner and
   * the backend exposes POST /api/demo/seed. Never auto-seeds data
   * unless this is on and the operator explicitly calls the seed.
   */
  demoMode: readBool("NEXT_PUBLIC_DEMO_MODE", false),
}
