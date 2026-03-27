/**
 * Zustand store root — combines analysisSlice, settingsSlice, and uiSlice
 * using the spread combination pattern.
 *
 * Usage:
 *   import { useStore } from '@/store';
 *   const ticker = useStore((s) => s.ticker);
 *
 * Per-slice convenience hooks are also exported for components that only need
 * a single slice, avoiding unnecessary re-renders from unrelated state changes.
 */

import { create } from 'zustand';
import { createAnalysisSlice, type AnalysisState } from './analysisSlice';
import { createSettingsSlice, type SettingsState } from './settingsSlice';
import { createUISlice, type UIState } from './uiSlice';

// ─── Combined store type ──────────────────────────────────────────────────────

export type StoreState = AnalysisState & SettingsState & UIState;

// ─── Store instance ───────────────────────────────────────────────────────────

export const useStore = create<StoreState>()((...args) => ({
  ...createAnalysisSlice(...args),
  ...createSettingsSlice(...args),
  ...createUISlice(...args),
}));

// ─── Convenience selectors ────────────────────────────────────────────────────

/** Hook that subscribes only to analysis state fields. */
export const useAnalysisStore = () =>
  useStore((s) => ({
    runId: s.runId,
    ticker: s.ticker,
    status: s.status,
    stepEvents: s.stepEvents,
    company: s.company,
    marketData: s.marketData,
    priceHistory: s.priceHistory,
    news: s.news,
    sentiment: s.sentiment,
    events: s.events,
    insights: s.insights,
    dataSources: s.dataSources,
    partialDataNotices: s.partialDataNotices,
    errorNotices: s.errorNotices,
    completeness: s.completeness,
    errorMessage: s.errorMessage,
    startAnalysis: s.startAnalysis,
    appendStepEvent: s.appendStepEvent,
    setPipelineComplete: s.setPipelineComplete,
    setPipelineFailed: s.setPipelineFailed,
    reset: s.reset,
  }));

/** Hook that subscribes only to settings state fields. */
export const useSettingsStore = () =>
  useStore((s) => ({
    openAiKey: s.openAiKey,
    openAiKeyStatus: s.openAiKeyStatus,
    activeModel: s.activeModel,
    setOpenAiKey: s.setOpenAiKey,
    clearOpenAiKey: s.clearOpenAiKey,
    markKeyInvalid: s.markKeyInvalid,
  }));

/** Hook that subscribes only to UI state fields. */
export const useUIStore = () =>
  useStore((s) => ({
    panelExpansion: s.panelExpansion,
    activeTimeframe: s.activeTimeframe,
    reasoningViewerExpanded: s.reasoningViewerExpanded,
    togglePanel: s.togglePanel,
    setTimeframe: s.setTimeframe,
    toggleReasoningViewer: s.toggleReasoningViewer,
  }));
