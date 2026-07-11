import { NextResponse } from "next/server"

/**
 * Active probe: only 200 if the FastAPI backend is reachable AND
 * /api/health returns ok. Otherwise 503.
 *
 * This is what the UI should poll to render the "system status" badge.
 * It is intentionally separate from the persisted-status GET so that
 * "is the backend up right now?" is never confused with "did the last
 * sync succeed?".
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function GET() {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 3000)
  try {
    const response = await fetch(`${API_URL.replace(/\/$/, "")}/api/health`, {
      signal: controller.signal,
      cache: "no-store",
    })
    clearTimeout(timeout)
    if (!response.ok) {
      return NextResponse.json(
        { success: false, error: { detail: `Backend /api/health returned ${response.status}` } },
        { status: 503 },
      )
    }
    const body = await response.json().catch(() => ({}))
    return NextResponse.json({ success: true, data: body })
  } catch (err) {
    clearTimeout(timeout)
    return NextResponse.json(
      {
        success: false,
        error: {
          detail: "Backend unreachable",
          message: err instanceof Error ? err.message : "unknown",
        },
      },
      { status: 503 },
    )
  }
}
