"use client"

import { env } from "@/lib/env"

/**
 * Persistent banner shown when NEXT_PUBLIC_DEMO_MODE is true. It is
 * NEVER shown in production builds. The point is to make sure no one
 * ever mistakes demo data for real business data.
 */
export function DemoBanner() {
  if (!env.demoMode) return null
  return (
    <div className="bg-amber-500/15 border-b border-amber-500/30 px-4 py-1.5 text-center text-xs font-medium text-amber-700 dark:text-amber-300">
      Demo restaurant — data is not real. Toggle with{" "}
      <code className="px-1 py-0.5 rounded bg-amber-500/20">NEXT_PUBLIC_DEMO_MODE</code>.
    </div>
  )
}
