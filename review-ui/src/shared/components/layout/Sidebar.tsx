import { useState, useCallback } from "react";
import { Activity, ChevronDown, ChevronUp, Database, Keyboard, LayoutDashboard, Mail, Settings as SettingsIcon } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useHotkeys } from "react-hotkeys-hook";

import { cn } from "@/shared/lib/cn";

const MAIN_NAV = [
  { to: "/", label: "Übersicht", icon: LayoutDashboard, end: true },
  { to: "/stammdaten", label: "Stammdaten", icon: Database, end: false },
  { to: "/status", label: "Status", icon: Activity, end: false },
  { to: "/mail-vorlage", label: "E-Mail & Dateiname", icon: Mail, end: false },
  { to: "/settings", label: "Einstellungen", icon: SettingsIcon, end: false },
] as const;

const SHORTCUTS = [
  { keys: ["Alt", "→"], label: "Nächster Schritt" },
  { keys: ["Alt", "←"], label: "Vorheriger Schritt" },
  { keys: ["Alt", "N"], label: "Neue Position" },
  { keys: ["Alt", "H"], label: "Datum heute" },
  { keys: ["Alt", "F"], label: "Vollbild" },
  { keys: ["Esc"], label: "Vollbild verlassen" },
];

interface SidebarProps {
  /** Optional slot for actions specific to the active page (e.g. reset). */
  pageActions?: React.ReactNode;
}

export function Sidebar({ pageActions }: SidebarProps) {
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const toggle = useCallback(() => setShortcutsOpen((v) => !v), []);

  useHotkeys("?", toggle, { useKey: true, preventDefault: true });

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
        {MAIN_NAV.map((item) => {
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

      <div className="border-t border-border">
        <button
          onClick={toggle}
          aria-expanded={shortcutsOpen}
          className="flex w-full items-center gap-3 px-6 py-3 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground"
        >
          <Keyboard className="h-3.5 w-3.5" aria-hidden="true" />
          Tastaturkürzel
          {shortcutsOpen
            ? <ChevronDown className="ml-auto h-3 w-3" />
            : <ChevronUp className="ml-auto h-3 w-3" />
          }
        </button>

        {shortcutsOpen && (
          <ul className="px-3 pb-3">
            {SHORTCUTS.map((s) => (
              <li
                key={s.label}
                className="flex items-center justify-between rounded-md px-3 py-1.5"
              >
                <span className="text-xs text-muted-foreground">{s.label}</span>
                <span className="flex items-center gap-0.5">
                  {s.keys.map((k) => (
                    <kbd
                      key={k}
                      className="inline-flex h-4 items-center rounded border border-border bg-muted px-1 font-mono text-[10px] font-semibold text-muted-foreground"
                    >
                      {k}
                    </kbd>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
