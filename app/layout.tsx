import type { Metadata } from "next"
import "./globals.css"
import { Sidebar } from "@/components/sidebar"
import { QueryProvider } from "@/lib/query-provider"
import { DemoBanner } from "@/components/demo-banner"

export const metadata: Metadata = {
  title: "RestaurantOS",
  description: "Restaurant management with inventory intelligence",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <QueryProvider>
          <DemoBanner />
          <div className="flex h-screen bg-background">
            <Sidebar />
            <main className="flex-1 overflow-y-auto">{children}</main>
          </div>
        </QueryProvider>
      </body>
    </html>
  )
}
