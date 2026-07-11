"use client"

import { useQuery } from "@tanstack/react-query"

/**
 * System health probe. Polls the Next.js /api/sync/health route, which
 * in turn calls the FastAPI /api/health endpoint. The dashboard reads
 * the result and renders an honest badge instead of a hardcoded
 * "Operational" string.
 */
export interface SystemHealth {
  ok: boolean
  backend_status: string | null
  backend_db: boolean | null
  detail: string | null
  ts: string
}

export const systemKeys = {
  health: ["system", "health"] as const,
  sync: ["system", "sync"] as const,
}

export function useSystemHealth() {
  return useQuery({
    queryKey: systemKeys.health,
    queryFn: async (): Promise<SystemHealth> => {
      try {
        const r = await fetch("/api/sync/health", { cache: "no-store" })
        const body = await r.json()
        return {
          ok: r.ok && body?.success === true,
          backend_status: body?.data?.status ?? null,
          backend_db: body?.data?.db ?? null,
          detail: body?.error?.detail ?? null,
          ts: body?.data?.ts ?? new Date().toISOString(),
        }
      } catch (e) {
        return {
          ok: false,
          backend_status: null,
          backend_db: null,
          detail: e instanceof Error ? e.message : "Network error",
          ts: new Date().toISOString(),
        }
      }
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export interface SyncStatus {
  last_success: string | null
  last_error: string | null
}

export function useSyncStatus() {
  return useQuery({
    queryKey: systemKeys.sync,
    queryFn: async (): Promise<SyncStatus> => {
      const r = await fetch("/api/sync", { cache: "no-store" })
      const body = await r.json()
      return {
        last_success: body?.data?.last_success ?? body?.last_success ?? null,
        last_error: body?.data?.last_error ?? null,
      }
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}
