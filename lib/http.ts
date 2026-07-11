/**
 * Low-level typed HTTP client for the FastAPI backend.
 *
 * Every backend response follows `ApiResponse<T>`:
 *
 *   { success: true, data: T }
 *   { success: false, error: { detail, error_id? } }
 *
 * On the wire, errors come back as proper HTTP status codes
 * (4xx/5xx). This client throws an `ApiError` for non-2xx responses so
 * TanStack Query's retry / error-handling machinery kicks in.
 */
import { env } from "./env"

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown
  readonly errorId: string | null

  constructor(status: number, detail: unknown, errorId: string | null) {
    const msg =
      typeof detail === "string"
        ? detail
        : (detail as { message?: string })?.message ?? `HTTP ${status}`
    super(msg)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
    this.errorId = errorId
  }
}

interface SuccessEnvelope<T> {
  success: true
  data: T
}

interface ErrorEnvelope {
  success: false
  error: { detail: unknown; error_id?: string }
}

export type ApiEnvelope<T> = SuccessEnvelope<T> | ErrorEnvelope

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${env.apiUrl.replace(/\/$/, "")}${path}`
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  })

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Non-JSON body. Surface as a generic error.
    if (!response.ok) {
      throw new ApiError(response.status, `Non-JSON error response`, null)
    }
    return null as T
  }

  if (!response.ok) {
    const errEnv = body as ErrorEnvelope | null
    const detail = errEnv?.error?.detail ?? body
    const errorId = errEnv?.error?.error_id ?? null
    throw new ApiError(response.status, detail, errorId)
  }

  const okEnv = body as ApiEnvelope<T> | null
  if (okEnv && okEnv.success === true) return okEnv.data
  if (okEnv && okEnv.success === false) {
    throw new ApiError(response.status, okEnv.error.detail, okEnv.error.error_id ?? null)
  }
  // Bare payload (no envelope) — accept it as-is.
  return body as T
}

export const http = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
      headers,
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
}
