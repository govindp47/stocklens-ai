'use client';

/**
 * NewsSummaryPanel — renders AI-summarised news article cards.
 *
 * Accessibility:
 * - External links have target="_blank" and rel="noopener noreferrer".
 * - Empty state uses a descriptive text with a newspaper icon.
 */

import { Newspaper, ExternalLink } from 'lucide-react';
import { useAnalysisStore } from '@/store';
import { Panel } from '@/components/ui/Panel';
import { PanelSkeleton } from '@/components/ui/PanelSkeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { SentimentBadge } from '@/components/ui/SentimentBadge';
import { formatDateTime } from '@/lib/formatters';
import type { ArticleSummary } from '@/types/report';

// ─── Article card ─────────────────────────────────────────────────────────────

function ArticleCard({ article }: { article: ArticleSummary }) {
  return (
    <article className="border-b border-neutral-100 last:border-0 px-4 py-3">
      {/* Title + external link */}
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="group inline-flex items-start gap-1 text-sm font-medium text-neutral-800 hover:text-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded"
        data-testid="news-article-link"
        aria-label={`Read article: ${article.title} (opens in new tab)`}
      >
        <span>{article.title}</span>
        <ExternalLink
          className="w-3 h-3 mt-0.5 shrink-0 text-neutral-400 group-hover:text-brand-500"
          aria-hidden="true"
        />
      </a>

      {/* Meta row: source + date */}
      <div className="flex items-center gap-2 mt-1">
        <span className="text-xs text-neutral-500">{article.source_name}</span>
        <span className="text-xs text-neutral-300">·</span>
        <span className="text-xs text-neutral-400">
          {formatDateTime(article.published_at)}
        </span>
      </div>

      {/* AI summary */}
      {!article.summarization_failed && article.summary && (
        <p className="mt-1.5 text-xs text-neutral-600 leading-relaxed">
          {article.summary}
        </p>
      )}

      {/* Topic badges + sentiment badge */}
      {(article.topics.length > 0 || article.sentiment) && (
        <div className="flex flex-wrap items-center gap-1 mt-2">
          {article.topics.map((topic) => (
            <span
              key={topic}
              className="px-1.5 py-0.5 rounded text-xs bg-neutral-100 text-neutral-600"
            >
              {topic}
            </span>
          ))}
          {article.sentiment && (
            <SentimentBadge sentiment={article.sentiment} />
          )}
        </div>
      )}
    </article>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function NewsEmptyState({ ticker }: { ticker: string }) {
  return (
    <div className="p-6 text-center">
      <Newspaper
        className="mx-auto w-8 h-8 text-neutral-300 mb-2"
        aria-hidden="true"
      />
      <p className="text-sm text-neutral-500">
        No recent news found for {ticker}.
      </p>
    </div>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function NewsSummaryPanel() {
  const { news, ticker, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!news) return 'loading';
    if (!news.available) return 'unavailable';
    return 'populated';
  })();

  const isLoading = status === 'loading' || status === 'streaming';

  return (
    <Panel id="news_summary" title="Recent News" status={panelStatus}>
      {!news && isLoading ? (
        <PanelSkeleton rows={4} />
      ) : !news || !news.available ? (
        <ErrorState message="News could not be retrieved at this time." />
      ) : news.articles.length === 0 ? (
        <NewsEmptyState ticker={ticker} />
      ) : (
        <div>
          {news.articles.map((article) => (
            <ArticleCard key={article.article_id} article={article} />
          ))}
        </div>
      )}
    </Panel>
  );
}
