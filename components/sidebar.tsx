"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { ChefHat, Home, Package, ShoppingCart } from "lucide-react"
import { useIngredients } from "@/lib/queries"
import { cn } from "@/lib/utils"

const navigation = [
  { name: "Dashboard", href: "/", icon: Home },
  { name: "Inventory", href: "/inventory", icon: Package },
  { name: "Orders", href: "/orders", icon: ShoppingCart },
]

// Phase 0: only Dashboard, Inventory, Orders. Analytics / Reports /
// Predictions / Kitchen / Settings are intentionally NOT in the nav
// until they have real backend implementations.

export function Sidebar() {
  const pathname = usePathname()
  const { data: ingredients = [] } = useIngredients()
  const lowStockCount = ingredients.filter((i) => i.quantity_today <= i.min_threshold).length

  return (
    <aside className="w-56 shrink-0 border-r border-sidebar-border bg-sidebar flex flex-col">
      <div className="h-16 px-6 flex items-center gap-2 border-b border-sidebar-border">
        <div className="w-8 h-8 rounded-lg bg-sidebar-primary flex items-center justify-center">
          <ChefHat className="w-5 h-5 text-sidebar-primary-foreground" />
        </div>
        <span className="font-semibold text-sidebar-foreground">RestaurantOS</span>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {navigation.map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon className="w-4 h-4" />
              <span>{item.name}</span>
              {item.name === "Inventory" && lowStockCount > 0 ? (
                <span className="ml-auto text-xs bg-destructive text-destructive-foreground rounded-full px-2 py-0.5">
                  {lowStockCount}
                </span>
              ) : null}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
