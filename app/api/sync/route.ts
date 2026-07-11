import { NextResponse } from "next/server"
import { promises as fs } from "node:fs"
import path from "node:path"

/**
 * RestaurantOS sync route.
 *
 * Previous behaviour: returned HTTP 200 with `success: true` even when
 * the FastAPI backend was unreachable. That's exactly the kind of fake
 * success that destroyed operator trust.
 *
 * New behaviour:
 *   - 200 on success: real FastAPI response is proxied back with
 *     last_success timestamp.
 *   - 503 when the backend is unreachable: returns a structured error
 *     including the last known success time (so the UI can show
 *     "Last successful sync: 8:42 PM — current: failed").
 *   - 500 on any other unexpected error.
 *
 * Persistent state (last_success) is written to a small JSON file in
 * `.next/cache/sync-status.json` so it survives reloads. In a real
 * deployment this should be a DB row or Redis, but the cache file is
 * enough for Phase 0 single-instance setups.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const STATUS_FILE = path.join(process.cwd(), ".next", "cache", "sync-status.json")

interface SyncStatusFile {
  last_success: string | null
  last_error: string | null
  last_error_id: string | null
}

async function readStatus(): Promise<SyncStatusFile> {
  try {
    const raw = await fs.readFile(STATUS_FILE, "utf-8")
    const parsed = JSON.parse(raw)
    return {
      last_success: parsed.last_success ?? null,
      last_error: parsed.last_error ?? null,
      last_error_id: parsed.last_error_id ?? null,
    }
  } catch {
    return { last_success: null, last_error: null, last_error_id: null }
  }
}

async function writeStatus(status: SyncStatusFile): Promise<void> {
  await fs.mkdir(path.dirname(STATUS_FILE), { recursive: true })
  await fs.writeFile(STATUS_FILE, JSON.stringify(status, null, 2))
}

function newErrorId(): string {
  return Math.random().toString(36).slice(2, 14)
}

export async function POST() {
  const status = await readStatus()
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch(`${API_URL.replace(/\/$/, "")}/api/sync`, {
      method: "POST",
      signal: controller.signal,
    })
    clearTimeout(timeout)
    if (!response.ok) {
      const errorId = newErrorId()
      const newStatus: SyncStatusFile = {
        ...status,
        last_error: `Backend returned ${response.status}`,
        last_error_id: errorId,
      }
      await writeStatus(newStatus)
      return NextResponse.json(
        {
          success: false,
          error: { detail: "Backend sync failed", error_id: errorId },
          last_success: status.last_success,
        },
        { status: 502 },
      )
    }
    const data = await response.json().catch(() => ({}))
    const now = new Date().toISOString()
    await writeStatus({ last_success: now, last_error: null, last_error_id: null })
    return NextResponse.json({
      success: true,
      data: data?.data ?? data,
      last_success: now,
    })
  } catch (err) {
    clearTimeout(timeout)
    const errorId = newErrorId()
    const message = err instanceof Error ? err.message : "Unknown error"
    await writeStatus({ ...status, last_error: message, last_error_id: errorId })
    return NextResponse.json(
      {
        success: false,
        error: { detail: "Backend unreachable", error_id: errorId, message },
        last_success: status.last_success,
      },
      { status: 503 },
    )
  }
}

export async function GET() {
  const status = await readStatus()
  return NextResponse.json({
    success: true,
    data: {
      last_success: status.last_success,
      last_error: status.last_error,
      last_error_id: status.last_error_id,
      // We deliberately do NOT compute a 'healthy' flag here; that's the
      // job of the /api/sync/health route which actively probes the
      // backend. This endpoint is purely a read of the last attempt.
    },
  })
}
