import { create } from "zustand";

import { calculateChangedFields } from "../lib/changedFields";
import type { Anfrage } from "@/shared/schemas/anfrage";
import type { ManualOverride } from "@/shared/schemas/quotation";

export interface ReviewSnapshot {
  anfrage: Anfrage;
  manualOverrides: ManualOverride[];
}

const MAX_HISTORY_ITEMS = 50;

/**
 * Per-review UI store.
 *
 * Holds **only** UI-flag state (changed-fields tracker, approval-actor
 * draft, focus mode). Server-state — Anfrage, Matches, Quotation,
 * Approval — lives entirely in TanStack Query's cache.
 *
 * State is reset whenever a different review is opened (see
 * `setActiveReview`).
 */

interface ReviewUiState {
  activeReviewId: string | null;
  originalAnfrage: Anfrage | null;
  currentAnfrage: Anfrage | null;
  manualOverrides: ManualOverride[];
  undoStack: ReviewSnapshot[];
  redoStack: ReviewSnapshot[];
  changedFields: Set<string>;
  approvalActor: string;
  resetConfirmPending: boolean;

  setActiveReview: (id: string | null) => void;
  syncReviewChanges: (
    originalAnfrage: Anfrage | null | undefined,
    currentAnfrage: Anfrage,
    manualOverrides: ManualOverride[],
  ) => void;
  refreshChangedFields: (
    currentAnfrage: Anfrage,
    manualOverrides?: ManualOverride[],
  ) => void;
  recordUndoSnapshot: () => void;
  undoSnapshot: () => ReviewSnapshot | null;
  redoSnapshot: () => ReviewSnapshot | null;
  trackChange: (fieldPath: string) => void;
  clearChanges: () => void;
  setApprovalActor: (name: string) => void;
  setResetConfirmPending: (v: boolean) => void;
}

export const useReviewUiStore = create<ReviewUiState>((set, get) => ({
  activeReviewId: null,
  originalAnfrage: null,
  currentAnfrage: null,
  manualOverrides: [],
  undoStack: [],
  redoStack: [],
  changedFields: new Set(),
  approvalActor: "",
  resetConfirmPending: false,

  setActiveReview: (id) => {
    if (get().activeReviewId === id) return;
    set({
      activeReviewId: id,
      originalAnfrage: null,
      currentAnfrage: null,
      manualOverrides: [],
      undoStack: [],
      redoStack: [],
      changedFields: new Set(),
      approvalActor: "",
      resetConfirmPending: false,
    });
  },

  syncReviewChanges: (originalAnfrage, currentAnfrage, manualOverrides) => {
    const baseline = originalAnfrage ?? currentAnfrage;
    set({
      originalAnfrage: baseline,
      currentAnfrage,
      manualOverrides,
      changedFields: calculateChangedFields(
        baseline,
        currentAnfrage,
        manualOverrides,
      ),
    });
  },

  refreshChangedFields: (currentAnfrage, manualOverrides) => {
    const state = get();
    if (!state.originalAnfrage) return;
    const nextOverrides = manualOverrides ?? state.manualOverrides;
    set({
      currentAnfrage,
      manualOverrides: nextOverrides,
      changedFields: calculateChangedFields(
        state.originalAnfrage,
        currentAnfrage,
        nextOverrides,
      ),
    });
  },

  recordUndoSnapshot: () => {
    const state = get();
    if (!state.currentAnfrage) return;
    const snapshot = cloneSnapshot({
      anfrage: state.currentAnfrage,
      manualOverrides: state.manualOverrides,
    });
    const previous = state.undoStack[state.undoStack.length - 1];
    if (previous && sameSnapshot(previous, snapshot)) {
      return;
    }
    set({
      undoStack: [...state.undoStack, snapshot].slice(-MAX_HISTORY_ITEMS),
      redoStack: [],
    });
  },

  undoSnapshot: () => {
    const state = get();
    if (!state.currentAnfrage || state.undoStack.length === 0) return null;
    const target = state.undoStack[state.undoStack.length - 1];
    const current = cloneSnapshot({
      anfrage: state.currentAnfrage,
      manualOverrides: state.manualOverrides,
    });
    const nextUndoStack = state.undoStack.slice(0, -1);
    const nextRedoStack = [...state.redoStack, current].slice(-MAX_HISTORY_ITEMS);
    set({
      currentAnfrage: target.anfrage,
      manualOverrides: target.manualOverrides,
      changedFields: calculateChangedFields(
        state.originalAnfrage,
        target.anfrage,
        target.manualOverrides,
      ),
      undoStack: nextUndoStack,
      redoStack: nextRedoStack,
    });
    return cloneSnapshot(target);
  },

  redoSnapshot: () => {
    const state = get();
    if (!state.currentAnfrage || state.redoStack.length === 0) return null;
    const target = state.redoStack[state.redoStack.length - 1];
    const current = cloneSnapshot({
      anfrage: state.currentAnfrage,
      manualOverrides: state.manualOverrides,
    });
    const nextRedoStack = state.redoStack.slice(0, -1);
    const nextUndoStack = [...state.undoStack, current].slice(-MAX_HISTORY_ITEMS);
    set({
      currentAnfrage: target.anfrage,
      manualOverrides: target.manualOverrides,
      changedFields: calculateChangedFields(
        state.originalAnfrage,
        target.anfrage,
        target.manualOverrides,
      ),
      undoStack: nextUndoStack,
      redoStack: nextRedoStack,
    });
    return cloneSnapshot(target);
  },

  trackChange: (fieldPath) =>
    set((state) => {
      if (state.changedFields.has(fieldPath)) return state;
      const next = new Set(state.changedFields);
      next.add(fieldPath);
      return { changedFields: next };
    }),

  clearChanges: () => set({ changedFields: new Set() }),

  setApprovalActor: (name) => set({ approvalActor: name }),

  setResetConfirmPending: (v) => set({ resetConfirmPending: v }),
}));

function cloneSnapshot(snapshot: ReviewSnapshot): ReviewSnapshot {
  return JSON.parse(JSON.stringify(snapshot)) as ReviewSnapshot;
}

function sameSnapshot(a: ReviewSnapshot, b: ReviewSnapshot): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
