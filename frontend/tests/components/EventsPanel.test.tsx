/**
 * EventsPanel acceptance tests.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// ─── Empty state mock ──────────────────────────────────────────────────────────

vi.mock('@/store', () => ({
  useAnalysisStore: () => ({
    events: { available: true, events: [] },
    status: 'complete',
  }),
  useUIStore: () => ({
    panelExpansion: { events: true },
    togglePanel: vi.fn(),
  }),
}));

import { EventsPanel } from '@/components/panels/EventsPanel';

describe('EventsPanel empty state', () => {
  it('renders the exact empty state string', () => {
    render(<EventsPanel />);
    expect(
      screen.getByText('No significant events identified.'),
    ).toBeDefined();
  });
});
