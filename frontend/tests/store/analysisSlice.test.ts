/**
 * analysisSlice unit tests.
 */

import { describe, it, expect } from 'vitest';
import { create } from 'zustand';
import { createAnalysisSlice } from '@/store/analysisSlice';
import { createSettingsSlice } from '@/store/settingsSlice';
import { createUISlice } from '@/store/uiSlice';
import type { StoreState } from '@/store';
import type { StepEvent } from '@/types/pipeline';

function createTestStore() {
  return create<StoreState>()((...args) => ({
    ...createAnalysisSlice(...args),
    ...createSettingsSlice(...args),
    ...createUISlice(...args),
  }));
}

function makeStepEvent(overrides: Partial<StepEvent> = {}): StepEvent {
  return {
    event_type: 'step_event',
    run_id: 'test-run-id',
    step: 'ticker_validation',
    status: 'completed',
    timestamp: '2026-03-30T12:00:00Z',
    ...overrides,
  };
}

describe('analysisSlice', () => {
  it('starts with idle status and empty stepEvents', () => {
    const store = createTestStore();
    expect(store.getState().status).toBe('idle');
    expect(store.getState().stepEvents).toHaveLength(0);
    expect(store.getState().runId).toBeNull();
  });

  it('startAnalysis sets ticker and status to loading', () => {
    const store = createTestStore();
    store.getState().startAnalysis('AAPL');
    expect(store.getState().ticker).toBe('AAPL');
    expect(store.getState().status).toBe('loading');
  });

  it('startAnalysis uppercases and trims the ticker', () => {
    const store = createTestStore();
    store.getState().startAnalysis('  aapl  ');
    expect(store.getState().ticker).toBe('AAPL');
  });

  it('appends step events in order', () => {
    const store = createTestStore();
    store.getState().startAnalysis('AAPL');
    store.getState().appendStepEvent(makeStepEvent({ step: 'ticker_validation' }));
    store.getState().appendStepEvent(makeStepEvent({ step: 'market_data_collection' }));
    expect(store.getState().stepEvents).toHaveLength(2);
    expect(store.getState().stepEvents[0].step).toBe('ticker_validation');
    expect(store.getState().stepEvents[1].step).toBe('market_data_collection');
  });

  it('appendStepEvent transitions status to streaming', () => {
    const store = createTestStore();
    store.getState().startAnalysis('AAPL');
    expect(store.getState().status).toBe('loading');
    store.getState().appendStepEvent(makeStepEvent());
    expect(store.getState().status).toBe('streaming');
  });

  it('reset clears all state to initial values', () => {
    const store = createTestStore();
    store.getState().startAnalysis('AAPL');
    store.getState().appendStepEvent(makeStepEvent());
    store.getState().reset();
    expect(store.getState().stepEvents).toHaveLength(0);
    expect(store.getState().runId).toBeNull();
    expect(store.getState().ticker).toBe('');
    expect(store.getState().status).toBe('idle');
  });

  it('setPipelineFailed sets status to failed with message', () => {
    const store = createTestStore();
    store.getState().startAnalysis('AAPL');
    store.getState().setPipelineFailed({ reason: 'Ticker not found' });
    expect(store.getState().status).toBe('failed');
    expect(store.getState().errorMessage).toBe('Ticker not found');
  });
});
