import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/shared/components/layout/AppShell";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { StammdatenPage } from "@/features/stammdaten/StammdatenPage";
import { ReviewDetailPage } from "@/features/review/ReviewDetailPage";

import { LegacyQueryRedirect } from "./LegacyQueryRedirect";

/**
 * App routes.
 *
 * Step routes are children of the review-detail route so the hero,
 * KPI strip and step indicator can render once and the inner step
 * is swapped via <Outlet />.
 */
export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      {
        path: "/",
        element: (
          <>
            <LegacyQueryRedirect />
            <DashboardPage />
          </>
        ),
      },
      { path: "/stammdaten", element: <StammdatenPage /> },
      { path: "/settings", element: <SettingsPage /> },
      {
        path: "/reviews/:reviewId",
        element: <ReviewDetailPage />,
        children: [
          { index: true, element: <Navigate to="positions" replace /> },
          { path: "positions", lazy: () => import("./lazy/positions") },
          { path: "customer", lazy: () => import("./lazy/customer") },
          { path: "approval", lazy: () => import("./lazy/approval") },
        ],
      },
    ],
  },
  // Catch-all → dashboard.
  { path: "*", element: <Navigate to="/" replace /> },
]);
