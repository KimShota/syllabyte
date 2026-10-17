/**
 * App state, in memory for now. Plan question 5 (AsyncStorage vs SecureStore, and the mock API until
 * the Phase 1 backend) decides where it persists; until then a reload starts the demo over.
 */
import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";
import { INITIALLY_WATCHED } from "@/data/course";
import type { Choice, Note } from "@/data/types";

export const SPEEDS = [0.75, 1, 1.25, 1.5, 2] as const;
export type Speed = (typeof SPEEDS)[number];

/** "1.0x", "1.25x" */
export function speedLabel(s: Speed): string {
  return `${Number.isInteger(s) ? s.toFixed(1) : s}x`;
}

export interface AppState {
  /** finished the first-run flow (welcome, analysis, baseline check) */
  onboarded: boolean;
  watched: string[];
  notes: Note[];
  prefs: { captions: boolean; speed: Speed };
  quizAnswers: Record<string, Choice>;
  /** "Notify when ready" on a drafting KU */
  notifyKuIds: string[];
}

const initialState: AppState = {
  onboarded: false,
  watched: INITIALLY_WATCHED,
  notes: [
    {
      id: "seed-1",
      kuId: "ku-individual-causal-effect",
      at: 70,
      text: "τ_i = Y_i(1) − Y_i(0): the individual treatment effect can't be observed, because both outcomes never happen at once. The fundamental problem of causal inference.",
      createdAt: 0,
    },
  ],
  prefs: { captions: true, speed: 1 },
  quizAnswers: {},
  notifyKuIds: [],
};

type Action =
  | { type: "finishOnboarding" }
  | { type: "markWatched"; kuId: string }
  | { type: "addNote"; note: Note }
  | { type: "editNote"; id: string; text: string }
  | { type: "deleteNote"; id: string }
  | { type: "setCaptions"; on: boolean }
  | { type: "setSpeed"; speed: Speed }
  | { type: "answer"; itemId: string; choice: Choice }
  | { type: "resetQuiz" }
  | { type: "toggleNotify"; kuId: string }
  | { type: "signOut" };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "finishOnboarding":
      return { ...state, onboarded: true };
    case "markWatched":
      return state.watched.includes(action.kuId) ? state : { ...state, watched: [...state.watched, action.kuId] };
    case "addNote":
      return { ...state, notes: [...state.notes, action.note] };
    case "editNote":
      return { ...state, notes: state.notes.map((n) => (n.id === action.id ? { ...n, text: action.text } : n)) };
    case "deleteNote":
      return { ...state, notes: state.notes.filter((n) => n.id !== action.id) };
    case "setCaptions":
      return { ...state, prefs: { ...state.prefs, captions: action.on } };
    case "setSpeed":
      return { ...state, prefs: { ...state.prefs, speed: action.speed } };
    case "answer":
      return { ...state, quizAnswers: { ...state.quizAnswers, [action.itemId]: action.choice } };
    case "resetQuiz":
      return { ...state, quizAnswers: {} };
    case "toggleNotify":
      return {
        ...state,
        notifyKuIds: state.notifyKuIds.includes(action.kuId)
          ? state.notifyKuIds.filter((id) => id !== action.kuId)
          : [...state.notifyKuIds, action.kuId],
      };
    case "signOut":
      return initialState;
  }
}

const StoreContext = createContext<{ state: AppState; dispatch: (a: Action) => void } | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore outside StoreProvider");
  return ctx;
}
