'use client';

/**
 * InsightPanel — AI-generated research overview divided into six named sections.
 *
 * Accessibility:
 * - Sections with insufficient data are rendered with muted/italic styling.
 * - Disclaimer is always visible at the bottom with role="note".
 */

import { useAnalysisStore } from '@/store';
import { Panel } from '@/components/ui/Panel';
import { PanelSkeleton } from '@/components/ui/PanelSkeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { DISCLAIMER_TEXT } from '@/lib/constants';
import type { InsightSections } from '@/types/report';

// ─── Fallback string that signals insufficient data ────────────────────────────

const INSUFFICIENT_DATA_SENTINEL = 'Insufficient data available for this section';

// ─── Section config ───────────────────────────────────────────────────────────

const SECTION_ORDER: Array<{ key: keyof InsightSections; label: string }> = [
  { key: 'company_overview',    label: 'Company Overview'    },
  { key: 'recent_developments', label: 'Recent Developments' },
  { key: 'sentiment_overview',  label: 'Sentiment Overview'  },
  { key: 'potential_drivers',   label: 'Potential Drivers'   },
  { key: 'potential_risks',     label: 'Potential Risks'     },
  { key: 'ai_summary',          label: 'AI Summary'          },
];

// ─── Single section ───────────────────────────────────────────────────────────

function InsightSection({
  label,
  content,
}: {
  label: string;
  content: string;
}) {
  const isInsufficient = content.includes(INSUFFICIENT_DATA_SENTINEL);

  return (
    <div className="border-b border-neutral-100 last:border-0 px-4 py-3">
      <h3 className="text-xs font-semibold text-neutral-700 mb-1">{label}</h3>
      <p
        className={
          isInsufficient
            ? 'text-xs text-neutral-400 italic'
            : 'text-xs text-neutral-700 leading-relaxed'
        }
      >
        {content}
      </p>
    </div>
  );
}

// ─── Disclaimer banner ────────────────────────────────────────────────────────

function InsightDisclaimer({ text }: { text: string }) {
  return (
    <div
      role="note"
      className="mx-4 mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
      data-testid="insight-disclaimer"
    >
      {text}
    </div>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function InsightPanel() {
  const { insights, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!insights) return 'loading';
    if (!insights.available) return 'unavailable';
    return 'populated';
  })();

  const isLoading = status === 'loading' || status === 'streaming';

  return (
    <Panel id="insights" title="AI Research Overview" status={panelStatus}>
      {!insights && isLoading ? (
        <PanelSkeleton rows={6} />
      ) : !insights || !insights.available || !insights.sections ? (
        <ErrorState message="AI insights could not be generated. Other data is still available." />
      ) : (
        <div>
          {SECTION_ORDER.map(({ key, label }) => (
            <InsightSection
              key={key}
              label={label}
              content={insights.sections![key]}
            />
          ))}

          {/* Disclaimer — always rendered at the bottom */}
          <InsightDisclaimer text={insights.disclaimer || DISCLAIMER_TEXT} />
        </div>
      )}
    </Panel>
  );
}
