import { Database, LayoutDashboard, Settings as SettingsIcon } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/shared/lib/cn";

const NAV = [
  { to: "/", label: "Übersicht", icon: LayoutDashboard, end: true },
  { to: "/stammdaten", label: "Stammdaten", icon: Database, end: false },
  { to: "/settings", label: "Einstellungen", icon: SettingsIcon, end: false },
] as const;

interface SidebarProps {
  /** Optional slot for actions specific to the active page (e.g. reset). */
  pageActions?: React.ReactNode;
}

export function Sidebar({ pageActions }: SidebarProps) {
  return (
    <aside className="hidden w-64 shrink-0 border-r border-border bg-surface lg:flex lg:flex-col">
      <div className="flex h-28 items-center px-6">
            <img
              src="/elringklinger-logo.png"
              alt="ElringKlinger"
              className="h-16 w-auto object-contain"
            />
          </div>
      <nav className="flex-1 space-y-1 px-3">
        <div className="section-label mb-2 px-3">Navigation</div>
        {NAV.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-semibold transition-colors",
                  isActive
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {pageActions && (
        <div className="border-t border-border px-4 py-4">
          <div className="section-label mb-3">Aktionen</div>
          {pageActions}
        </div>
      )}
    </aside>
  );
}
