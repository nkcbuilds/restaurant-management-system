import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex items-center justify-center h-full p-6">
      <div className="text-center space-y-4 max-w-md">
        <p className="text-6xl font-bold text-muted-foreground">404</p>
        <h1 className="text-2xl font-semibold">Page not found</h1>
        <p className="text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link href="/">
          <Button>Back to Dashboard</Button>
        </Link>
      </div>
    </div>
  )
}
