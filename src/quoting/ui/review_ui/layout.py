"""Visual layout for the Streamlit review UI.

Owns:
- The global stylesheet (``apply_style``)
- The Vollbild / focus-mode stylesheet (``apply_focus_style``)
- Sidebar variants for dashboard / review / settings pages

Design intent: stakeholder-grade polish with one ElringKlinger-red accent;
Inter Tight for display, Inter for body. Minimal emoji, professional
typography, dezente Status-Chips and consistent button styling.

The Review-ID lives in *one* place: the page header chip. The sidebar
no longer carries a duplicate review-id card.

Vollbild mode (used in step 3 only) hides the sidebar, breadcrumb,
step indicator, KPI strip and agent chat via CSS so the reviewer can
focus on side-by-side comparison and approval. Toggling is purely a
CSS overlay — the widget tree underneath is left untouched, so
state survives the round trip.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path

import streamlit as st

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


# --------------------------------------------------------------------- assets
def img_to_base64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode()


# --------------------------------------------------------------------- styles
_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Inter+Tight:wght@500;600;700;800;900&display=swap');

:root {
  --ek-bg:            #fafaf9;
  --ek-surface:       #ffffff;
  --ek-surface-2:     #f5f5f4;
  --ek-surface-sunk:  #f1f5f9;
  --ek-border:        #e5e7eb;
  --ek-border-strong: #d1d5db;
  --ek-divider:       #f1f5f9;
  --ek-text:          #0f172a;
  --ek-text-2:        #334155;
  --ek-muted:         #64748b;
  --ek-faint:         #94a3b8;
  --ek-brand:         #e30613;
  --ek-brand-dark:    #b8000b;
  --ek-brand-soft:    #fef2f2;
  --ek-accent:        #1e3a8a;
  --ek-accent-soft:   #eef2ff;
  --ek-success:       #047857;
  --ek-success-soft:  #ecfdf5;
  --ek-success-border:#a7f3d0;
  --ek-info:          #1d4ed8;
  --ek-info-soft:     #eff6ff;
  --ek-info-border:   #bfdbfe;
  --ek-warning:       #b45309;
  --ek-warning-soft:  #fff7ed;
  --ek-warning-border:#fde68a;
  --ek-danger:        #b91c1c;
  --ek-danger-soft:   #fef2f2;
  --ek-danger-border: #fecaca;

  --ek-shadow-1: 0 1px 2px rgba(15,23,42,0.04), 0 1px 1px rgba(15,23,42,0.02);
  --ek-shadow-2: 0 6px 20px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04);
  --ek-shadow-3: 0 24px 48px -12px rgba(15,23,42,0.18), 0 4px 8px rgba(15,23,42,0.04);
}

/* ---------------- Base ---------------- */
html, body, [data-testid="stAppViewContainer"] {
  font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
  background-color: var(--ek-bg);
  color: var(--ek-text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
[data-testid="stAppViewContainer"] > .main { background-color: var(--ek-bg); }

h1, h2, h3, h4, h5 {
  font-family: 'Inter Tight', 'Inter', sans-serif;
  color: var(--ek-text);
  letter-spacing: -0.02em;
}
h1 { font-weight: 800; }
h2, h3 { font-weight: 700; }

.block-container {
  padding-top: 0 !important;
  padding-bottom: 4rem !important;
  max-width: 1400px;
}

/* ---------------- Page title ---------------- */
.ek-title-block {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 8px;
  padding: 8px 0 0 0;
}
.ek-title {
  font-family: 'Inter Tight', sans-serif;
  font-size: 44px;
  line-height: 1.05;
  margin: 0;
  color: var(--ek-text);
  font-weight: 800;
  letter-spacing: -0.035em;
}
.ek-title .ek-accent-dot { color: var(--ek-brand); }

.ek-subtitle {
  margin: 0;
  color: var(--ek-muted);
  font-size: 15px;
  line-height: 1.5;
  max-width: 720px;
}

.ek-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
}

.ek-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 600;
  background: var(--ek-surface);
  border: 1px solid var(--ek-border);
  color: var(--ek-text-2);
}
.ek-chip-success {
  background: var(--ek-success-soft);
  border-color: var(--ek-success-border);
  color: var(--ek-success);
}
.ek-chip-brand {
  background: var(--ek-brand-soft);
  border-color: #fecaca;
  color: var(--ek-brand-dark);
}
.ek-chip-muted {
  background: var(--ek-surface-2);
  border-color: var(--ek-border);
  color: var(--ek-muted);
}
.ek-chip code {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  font-size: 11.5px;
  background: transparent;
  padding: 0;
  color: inherit;
}

.ek-pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
  display: inline-block;
}

/* ---------------- Process breadcrumb ----------------
   Slim trail above the page title that signals where the user is in
   the larger Outlook → Pipeline → Review flow. Three tiny pills
   joined by chevrons; the active node is filled, the others are
   muted. */
.ek-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ek-muted);
  letter-spacing: -0.005em;
}
.ek-breadcrumb-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--ek-surface-2);
  border: 1px solid var(--ek-border);
  color: var(--ek-muted);
}
.ek-breadcrumb-node.active {
  background: var(--ek-brand-soft);
  border-color: #fecaca;
  color: var(--ek-brand-dark);
}
.ek-breadcrumb-sep {
  color: var(--ek-faint);
  font-size: 11px;
}

/* ---------------- Workflow steps (review detail) ---------------- */
.ek-steps {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin: 22px 0 8px 0;
}
.ek-step {
  display: block;
  background: var(--ek-surface);
  border: 1px solid var(--ek-border);
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: var(--ek-shadow-1);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.06s ease;
  position: relative;
  overflow: hidden;
  color: inherit;
  text-decoration: none !important;
}
.ek-step.clickable {
  cursor: pointer;
}
.ek-step.clickable:hover {
  border-color: var(--ek-border-strong);
  box-shadow: var(--ek-shadow-2);
  text-decoration: none !important;
  transform: translateY(-1px);
}
.ek-step::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--ek-border);
}
.ek-step.active::before { background: var(--ek-brand); }
.ek-step.done::before   { background: var(--ek-success); }

.ek-step-num {
  font-family: 'Inter Tight', sans-serif;
  font-size: 13px;
  font-weight: 700;
  color: var(--ek-faint);
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}
.ek-step.active .ek-step-num { color: var(--ek-brand); }
.ek-step.done   .ek-step-num { color: var(--ek-success); }

.ek-step-title {
  font-family: 'Inter Tight', sans-serif;
  font-size: 16px;
  font-weight: 700;
  color: var(--ek-text);
  margin: 0 0 4px 0;
  letter-spacing: -0.01em;
}
.ek-step-desc {
  font-size: 13px;
  color: var(--ek-muted);
  line-height: 1.5;
  margin: 0;
}

/* ---------------- Sidebar ---------------- */
[data-testid="stSidebar"] {
  background-color: var(--ek-surface) !important;
  border-right: 1px solid var(--ek-divider);
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding-top: 8px !important;
}

.ek-sidebar-caption {
  color: var(--ek-muted);
  font-size: 12.5px;
  line-height: 1.55;
  margin-bottom: 24px;
  padding: 0 2px;
}

/* Sidebar nav buttons — muted, no icons, clean type. */
[data-testid="stSidebar"] .stButton > button {
  background: transparent !important;
  color: var(--ek-text-2) !important;
  border: 1px solid transparent !important;
  text-align: left !important;
  justify-content: flex-start !important;
  padding: 0.55rem 0.85rem !important;
  font-weight: 600 !important;
  font-size: 13.5px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--ek-surface-2) !important;
  border-color: var(--ek-border) !important;
  color: var(--ek-text) !important;
}

/* Danger zone in sidebar. Soft, but unmistakable. */
.ek-sidebar-danger {
  margin-top: 4px;
  padding: 12px 14px 10px 14px;
  background: var(--ek-danger-soft);
  border: 1px solid var(--ek-danger-border);
  border-radius: 10px;
}
.ek-sidebar-danger-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--ek-danger);
  letter-spacing: -0.005em;
  margin-bottom: 4px;
}
.ek-sidebar-danger-desc {
  font-size: 11.5px;
  color: var(--ek-text-2);
  line-height: 1.45;
  margin-bottom: 10px;
}
.ek-sidebar-danger-confirm {
  font-size: 11.5px;
  color: var(--ek-danger);
  font-weight: 600;
  margin: 4px 0 8px 0;
  line-height: 1.4;
}

/* Reset buttons inside the danger zone keep their own personality. */
.ek-sidebar-danger + div .stButton > button {
  background: var(--ek-surface) !important;
  border: 1px solid var(--ek-danger-border) !important;
  color: var(--ek-danger) !important;
  justify-content: center !important;
  text-align: center !important;
  font-weight: 700 !important;
}
.ek-sidebar-danger + div .stButton > button:hover {
  background: var(--ek-danger-soft) !important;
  border-color: var(--ek-danger) !important;
}
.ek-sidebar-danger + div .stButton > button[kind="primary"] {
  background: var(--ek-danger) !important;
  color: white !important;
  border-color: var(--ek-danger) !important;
}
.ek-sidebar-danger + div .stButton > button[kind="primary"]:hover {
  background: #991b1b !important;
  border-color: #991b1b !important;
}

/* ---------------- Buttons ---------------- */
.stButton > button, .stDownloadButton > button {
  border-radius: 10px !important;
  font-weight: 600 !important;
  padding: 0.65rem 1.2rem !important;
  border: 1px solid var(--ek-border-strong) !important;
  transition: all 0.16s ease !important;
  font-family: 'Inter', sans-serif !important;
  letter-spacing: -0.005em !important;
}
.stButton > button:hover {
  background: var(--ek-surface-2) !important;
  border-color: var(--ek-text-2) !important;
}
.stButton > button[kind="primary"], .stDownloadButton > button {
  background: var(--ek-text) !important;
  color: white !important;
  border-color: var(--ek-text) !important;
  box-shadow: 0 1px 2px rgba(0,0,0,0.08) !important;
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {
  background: #000 !important;
  border-color: #000 !important;
  transform: translateY(-1px);
  box-shadow: var(--ek-shadow-2) !important;
}

/* ---------------- Metrics ---------------- */
[data-testid="stMetric"] {
  background: var(--ek-surface);
  border: 1px solid var(--ek-border);
  border-radius: 14px;
  padding: 16px 18px;
  box-shadow: var(--ek-shadow-1);
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
[data-testid="stMetric"]:hover {
  border-color: var(--ek-border-strong);
  box-shadow: var(--ek-shadow-2);
}
[data-testid="stMetric"] [data-testid="stMetricLabel"] {
  color: var(--ek-muted);
  font-size: 12px !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
  font-family: 'Inter Tight', sans-serif !important;
  font-weight: 800 !important;
  font-size: 28px !important;
  color: var(--ek-text);
  letter-spacing: -0.025em;
}

/* ---------------- Expander / inputs / dataframe / chat ---------------- */
[data-testid="stExpander"] {
  background: var(--ek-surface);
  border: 1px solid var(--ek-border) !important;
  border-radius: 12px !important;
  box-shadow: var(--ek-shadow-1);
  overflow: hidden;
}
[data-testid="stExpander"] summary {
  font-weight: 600 !important;
  color: var(--ek-text) !important;
  padding: 12px 16px !important;
}

.stTextInput input, .stTextArea textarea, .stNumberInput input {
  border-radius: 8px !important;
  border-color: var(--ek-border) !important;
  font-family: 'Inter', sans-serif !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
  border-color: var(--ek-brand) !important;
  box-shadow: 0 0 0 3px rgba(227, 6, 19, 0.10) !important;
}

[data-testid="stDataFrame"] {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--ek-border);
  box-shadow: var(--ek-shadow-1);
}

[data-testid="stChatMessage"] {
  background: var(--ek-surface);
  border: 1px solid var(--ek-border);
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 8px;
  box-shadow: var(--ek-shadow-1);
}
[data-testid="stChatInput"] {
  border-radius: 12px;
  box-shadow: var(--ek-shadow-2);
}

/* ---------------- Misc ---------------- */
hr {
  border: none;
  border-top: 1px solid var(--ek-divider);
  margin: 24px 0 !important;
}

.ek-section-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--ek-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 0 0 12px 0;
}

/* ---------------- Pills ---------------- */
.ek-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px 3px 7px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
  border: 1px solid var(--ek-border);
}
.ek-pill-success {
  background: var(--ek-success-soft);
  color: var(--ek-success);
  border-color: var(--ek-success-border);
}
.ek-pill-info {
  background: var(--ek-info-soft);
  color: var(--ek-info);
  border-color: var(--ek-info-border);
}
.ek-pill-warning {
  background: var(--ek-warning-soft);
  color: var(--ek-warning);
  border-color: var(--ek-warning-border);
}
.ek-pill-neutral {
  background: var(--ek-surface-2);
  color: var(--ek-muted);
  border-color: var(--ek-border);
}

/* ---------------- Match summary + chips (Step 1) ---------------- */
.ek-match-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 2px 0;
  color: var(--ek-muted);
  font-size: 12px;
}
.ek-match-summary-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 7px;
  border-radius: 999px;
  background: transparent;
  color: var(--ek-muted);
}
.ek-match-summary-count {
  color: var(--ek-text-2);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}
.ek-match-summary-item.exact .ek-match-summary-count {
  color: var(--ek-success);
}
.ek-match-summary-item.fuzzy .ek-match-summary-count,
.ek-match-summary-item.semantic .ek-match-summary-count {
  color: var(--ek-info);
}
.ek-match-summary-item.no_match .ek-match-summary-count {
  color: var(--ek-warning);
}

.ek-match-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px 2px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.45;
  border: 1px solid var(--ek-border);
  background: transparent;
  color: var(--ek-muted);
  margin-bottom: 6px;
  max-width: 100%;
}
.ek-match-chip .ek-pill-dot {
  width: 5px;
  height: 5px;
  opacity: 0.65;
}
.ek-match-chip.exact {
  background: var(--ek-success-soft);
  border-color: var(--ek-success-border);
  color: var(--ek-success);
}
.ek-match-chip.fuzzy,
.ek-match-chip.semantic {
  background: var(--ek-info-soft);
  border-color: var(--ek-info-border);
  color: var(--ek-info);
}
.ek-match-chip.no_match {
  background: var(--ek-warning-soft);
  border-color: var(--ek-warning-border);
  color: var(--ek-warning);
}
.ek-match-chip-label {
  font-weight: 600;
}
.ek-match-chip-meta {
  color: inherit;
  opacity: 0.72;
  font-weight: 400;
}
.ek-match-chip-meta code {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  font-size: 11px;
  background: rgba(15,23,42,0.06);
  padding: 1px 5px;
  border-radius: 4px;
  color: inherit;
}

/* ---------------- Dashboard rows (compact) ---------------- */
.ek-review-card {
  background: var(--ek-surface);
  border: 1px solid var(--ek-border);
  border-radius: 12px;
  padding: 12px 14px 12px 16px;
  box-shadow: var(--ek-shadow-1);
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.06s ease;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  margin-bottom: 8px;
  cursor: pointer;
  position: relative;
}
.ek-review-card:hover {
  border-color: var(--ek-border-strong);
  box-shadow: var(--ek-shadow-2);
}
.ek-review-card:focus-within {
  outline: 3px solid rgba(227, 6, 19, 0.18);
  border-color: var(--ek-brand);
}
.ek-review-card-link {
  position: absolute;
  inset: 0;
  z-index: 1;
  border-radius: inherit;
  text-decoration: none !important;
}
.ek-review-main { min-width: 0; }

.ek-review-head-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}
.ek-review-id {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  font-size: 11px;
  color: var(--ek-muted);
  background: var(--ek-surface-2);
  border: 1px solid var(--ek-border);
  padding: 2px 8px;
  border-radius: 999px;
}
.ek-review-date {
  color: var(--ek-faint);
  font-size: 11.5px;
  font-weight: 600;
  text-align: right;
  white-space: nowrap;
}
.ek-review-subject {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--ek-text);
  line-height: 1.35;
  margin-bottom: 3px;
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ek-review-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
  color: var(--ek-muted);
  font-size: 12px;
}
.ek-review-meta-sep { color: var(--ek-faint); }

.ek-review-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 7px;
  min-width: 132px;
  position: relative;
  z-index: 2;
}
.ek-review-action {
  min-height: 34px;
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px solid var(--ek-border-strong);
  padding: 0 12px;
  color: var(--ek-text-2) !important;
  background: var(--ek-surface);
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  text-decoration: none !important;
  white-space: nowrap;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease,
              box-shadow 0.16s ease, transform 0.16s ease;
}
.ek-review-action:hover {
  border-color: var(--ek-text-2);
  background: var(--ek-surface-2);
  color: var(--ek-text) !important;
}
.ek-review-action-download {
  background: var(--ek-brand);
  border-color: var(--ek-brand);
  color: #fff !important;
  box-shadow: 0 1px 2px rgba(185,28,28,0.12);
}
.ek-review-action-download:hover {
  background: var(--ek-brand-dark);
  border-color: var(--ek-brand-dark);
  color: #fff !important;
  transform: translateY(-1px);
  box-shadow: var(--ek-shadow-2);
}

@media (max-width: 760px) {
  .ek-review-card {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 12px;
  }
  .ek-review-head-row {
    flex-wrap: wrap;
    gap: 7px;
  }
  .ek-review-date {
    text-align: left;
    width: 100%;
  }
  .ek-review-subject {
    white-space: normal;
  }
  .ek-review-actions {
    align-items: flex-start;
    justify-content: flex-start;
    min-width: 0;
  }
  .ek-review-action {
    min-height: 30px;
    padding-inline: 10px;
  }
}

/* ---------------- Preview shell (Step 1) ---------------- */
.ek-preview-shell {
  background: white;
  border: 1px solid var(--ek-border);
  border-radius: 14px;
  padding: 0;
  overflow: hidden;
  box-shadow: var(--ek-shadow-1);
}
.ek-preview-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--ek-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 10px 14px;
  background: var(--ek-surface-2);
  border-bottom: 1px solid var(--ek-border);
}
.ek-preview-iframe {
  width: 100%;
  height: 820px;
  border: 0;
  display: block;
  background: white;
}
.ek-preview-text {
  padding: 18px 22px;
  max-height: 760px;
  overflow-y: auto;
  font-family: 'Inter', sans-serif;
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--ek-text-2);
  white-space: pre-wrap;
  word-break: break-word;
}
.ek-mail-headers {
  padding: 14px 22px;
  background: linear-gradient(180deg, var(--ek-surface-2) 0%, white 100%);
  border-bottom: 1px solid var(--ek-divider);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ek-mail-header-row {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 12px;
  font-size: 13px;
}
.ek-mail-header-label {
  color: var(--ek-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 11px;
  padding-top: 2px;
}
.ek-mail-header-value {
  color: var(--ek-text);
  font-weight: 500;
  word-break: break-word;
}

/* ---------------- Side-by-side comparison (Step 3) ---------------- */
.ek-compare-pane-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--ek-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 0 0 8px 0;
}
.ek-preview-shell-compare {
  height: 820px;
  display: flex;
  flex-direction: column;
}
.ek-preview-shell-compare .ek-preview-iframe {
  height: auto;
  min-height: 0;
  flex: 1 1 auto;
}
.ek-preview-shell-compare .ek-preview-text {
  max-height: none;
  min-height: 0;
  flex: 1 1 auto;
}
.ek-preview-shell-compare .ek-mail-headers,
.ek-preview-shell-compare .ek-preview-title {
  flex: 0 0 auto;
}

/* ---------------- Changes indicator (editor) ---------------- */
.ek-changes-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, var(--ek-warning-soft) 0%, white 100%);
  border: 1px solid var(--ek-warning-border);
  color: var(--ek-warning);
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 12px;
}
</style>
"""


# --------------------------------------------------------------------- focus mode
#
# Vollbild collapses the whole "review chrome" to leave only the
# comparison + approval visible. We ship it as a separate stylesheet
# that only gets injected when the URL says ``?focus=1`` so the normal
# page is never affected.
_FOCUS_CSS = """
<style>
/* Hide everything that isn't comparison or approval. */
[data-testid="stSidebar"],
[data-testid="collapsedControl"] {
  display: none !important;
}

/* Reclaim full width for the side-by-side panes. */
.block-container {
  max-width: 100% !important;
  padding: 0.6rem 2rem 2rem 2rem !important;
}

/* Top toolbar: review id chip on the left, exit button on the right. */
.ek-focus-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--ek-surface);
  border: 1px solid var(--ek-border);
  border-radius: 12px;
  box-shadow: var(--ek-shadow-1);
  min-height: 44px;
}
.ek-focus-bar-title {
  font-family: 'Inter Tight', sans-serif;
  font-weight: 700;
  font-size: 14px;
  color: var(--ek-text);
  letter-spacing: -0.01em;
}
.ek-focus-bar-id {
  font-family: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  font-size: 11.5px;
  color: var(--ek-muted);
  background: var(--ek-surface-2);
  border: 1px solid var(--ek-border);
  padding: 2px 9px;
  border-radius: 999px;
}
.ek-focus-bar-file {
  font-size: 12px;
  color: var(--ek-muted);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Make the comparison panes use the available vertical space. */
.ek-preview-shell-compare {
  height: calc(100vh - 200px) !important;
  min-height: 600px;
}
</style>
"""


def apply_style() -> None:
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def apply_focus_style() -> None:
    """Inject the Vollbild overlay stylesheet on top of the global one."""
    st.markdown(_FOCUS_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------- sidebars
def _sidebar_logo() -> None:
    elring_logo = img_to_base64(ASSETS_DIR / "logo_elringklinger.png")
    if elring_logo:
        st.markdown(
            f'<img src="data:image/png;base64,{elring_logo}" '
            f'style="display: block; width: 100%; margin: 0 0 22px 0;" '
            f'alt="ElringKlinger">',
            unsafe_allow_html=True,
        )
    else:
        st.title("ElringKlinger")


def _sidebar_nav() -> None:
    """Navigation block: Übersicht / Einstellungen — text-only labels."""
    st.markdown(
        '<div class="ek-section-label" style="margin-top: 18px;">Navigation</div>',
        unsafe_allow_html=True,
    )

    if st.button("Übersicht", use_container_width=True, key="nav_dashboard"):
        st.query_params.clear()
        st.rerun()

    if st.button("Einstellungen", use_container_width=True, key="nav_settings"):
        st.query_params.clear()
        st.query_params["settings"] = "1"
        st.rerun()


def render_sidebar_dashboard():
    """Sidebar variant for the dashboard. Returns the uploaded file or None."""
    with st.sidebar:
        _sidebar_logo()

        st.markdown(
            '<div class="ek-section-label">Neue Anfrage hochladen</div>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "Anfrage hochladen",
            type=["pdf", "msg", "eml", "xlsx", "xls", "csv"],
            label_visibility="collapsed",
        )
        st.markdown(
            '<div class="ek-sidebar-caption" style="margin-top: 12px;">'
            "Alternativ kommen Anfragen automatisch über das Outlook Add-in "
            "in dieser Übersicht an."
            "</div>",
            unsafe_allow_html=True,
        )

        _sidebar_nav()

    return uploaded


def render_sidebar_review(
    action_renderer: Callable[[], None] | None = None,
) -> None:
    """Sidebar variant for the review-detail page.

    The active review-id is now shown only in the page header chip,
    so the sidebar carries just navigation and (optionally) actions.
    """
    with st.sidebar:
        _sidebar_logo()

        if action_renderer is not None:
            with st.expander("Weitere Aktionen", expanded=False):
                action_renderer()

        _sidebar_nav()


def render_sidebar_settings():
    """Sidebar for the settings page."""
    with st.sidebar:
        _sidebar_logo()

        st.markdown(
            '<div class="ek-section-label">Neue Anfrage hochladen</div>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "Anfrage hochladen",
            type=["pdf", "msg", "eml", "xlsx", "xls", "csv"],
            label_visibility="collapsed",
            key="settings_uploader",
        )
        st.markdown(
            '<div class="ek-sidebar-caption" style="margin-top: 12px;">'
            "Alternativ kommen Anfragen automatisch über das Outlook Add-in "
            "in dieser Übersicht an."
            "</div>",
            unsafe_allow_html=True,
        )

        _sidebar_nav()

    return uploaded
