/**
 * uiSlice — panel expansion state, active timeframe, and reasoning viewer toggle.
 */

import type { StateCreator } from 'zustand';
import type { StoreState } from './index';

// ─── Types ────────────────────────────────────────────────────────────────────

export type PanelId =
  | 'stock_overview'
  | 'price_chart'
  | 'news_summary'
  | 'sentiment'
  | 'events'
  | 'insights'
  | 'data_sources'
  | 'reasoning_viewer';

export type ActiveTimeframe = '1M' | '3M' | '6M' | '1Y';

// All panels start expanded.
const ALL_PANEL_IDS: PanelId[] = [
  'stock_overview',
  'price_chart',
  'news_summary',
  'sentiment',
  'events',
  'insights',
  'data_sources',
  'reasoning_viewer',
];

const defaultPanelExpansion: Record<PanelId, boolean> = Object.fromEntries(
  ALL_PANEL_IDS.map((id) => [id, true]),
) as Record<PanelId, boolean>;

// ─── State shape ─────────────────────────────────────────────────────────────

export interface UIState {
  panelExpansion: Record<PanelId, boolean>;
  activeTimeframe: ActiveTimeframe;
  reasoningViewerExpanded: boolean;

  togglePanel: (panelId: PanelId) => void;
  setTimeframe: (tf: ActiveTimeframe) => void;
  toggleReasoningViewer: () => void;
}

// ─── Initial state ────────────────────────────────────────────────────────────

const initialUIState = {
  panelExpansion: defaultPanelExpansion,
  activeTimeframe: '1M' as ActiveTimeframe,
  reasoningViewerExpanded: false,
};

// ─── Slice factory ────────────────────────────────────────────────────────────

export const createUISlice: StateCreator<StoreState, [], [], UIState> = (
  set,
) => ({
  ...initialUIState,

  togglePanel: (panelId: PanelId) =>
    set((state) => ({
      panelExpansion: {
        ...state.panelExpansion,
        [panelId]: !state.panelExpansion[panelId],
      },
    })),

  setTimeframe: (tf: ActiveTimeframe) => set({ activeTimeframe: tf }),

  toggleReasoningViewer: () =>
    set((state) => ({
      reasoningViewerExpanded: !state.reasoningViewerExpanded,
    })),
});
