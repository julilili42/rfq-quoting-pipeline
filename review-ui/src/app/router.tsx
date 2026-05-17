import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/shared/components/layout/AppShell";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import {
  DebugChecksPage,
  DebugLlmPage,
  DebugPage,
  DebugPipelinePage,
  DebugStammdatenPage,
} from "@/features/debug/DebugPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { MailVorlagePage } from "@/features/settings/MailVorlagePage";
import { StatusPage } from "@/features/status/StatusPage";
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
      { path: "/status", element: <StatusPage /> },
      { path: "/debug", element: <DebugPage /> },
      { path: "/debug/pipeline", element: <DebugPipelinePage /> },
      { path: "/debug/checks", element: <DebugChecksPage /> },
      { path: "/debug/llm", element: <DebugLlmPage /> },
      { path: "/debug/stammdaten", element: <DebugStammdatenPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "/mail-vorlage", element: <MailVorlagePage /> },
      {
        path: "/reviews/:reviewId",
        element: <ReviewDetailPage />,
        children: [
          { index: true, element: <Navigate to="positions" replace /> },
          { path: "positions", lazy: () => import("./lazy/positions") },
          { path: "customer", element: <Navigate to="../positions" replace /> },
          { path: "approval", lazy: () => import("./lazy/approval") },
        ],
      },
    ],
  },
  // Catch-all → dashboard.
  { path: "*", element: <Navigate to="/" replace /> },
]);
