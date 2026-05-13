import { Outlet, useSearchParams } from "react-router-dom";

import { Sidebar } from "./Sidebar";

export function AppShell() {
  const [searchParams] = useSearchParams();
  const focusMode = searchParams.get("focus") === "1";

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {!focusMode && <Sidebar />}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
