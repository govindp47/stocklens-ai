"use client";

/**
 * NewsSummaryPanel — renders AI-summarised news article cards.
 */

import { Newspaper, ExternalLink, Clock } from "lucide-react";
import { useAnalysisStore } from "@/store";
import { Panel } from "@/components/ui/Panel";
import { PanelSkeleton } from "@/components/ui/PanelSkeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { SentimentBadge } from "@/components/ui/SentimentBadge";
import { formatDateTime } from "@/lib/formatters";
import type { ArticleSummary } from "@/types/report";

// ─── Article card ─────────────────────────────────────────────────────────────

function ArticleCard({ article }: { article: ArticleSummary }) {
  return (
    <article className="group border-b border-border/50 last:border-0 px-4 py-4 hover:bg-muted/30 transition-colors duration-100">
      {/* Title */}
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-start gap-1.5 text-sm font-medium text-foreground
          hover:text-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded"
        data-testid="news-article-link"
        aria-label={`Read article: ${article.title} (opens in new tab)`}
      >
        <span className="leading-snug">{article.title}</span>
        <ExternalLink
          className="h-3 w-3 mt-1 shrink-0 text-muted-foreground group-hover:text-brand-500 transition-colors"
          aria-hidden="true"
        />
      </a>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
        <span className="text-xs font-medium text-muted-foreground">
          {article.source_name}
        </span>
        <span className="text-muted-foreground/40" aria-hidden="true">
          ·
        </span>
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" aria-hidden="true" />
          {formatDateTime(article.published_at)}
        </span>
        {article.deduplication_count != null &&
          article.deduplication_count > 1 && (
            <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {article.deduplication_count} sources
            </span>
          )}
      </div>

      {/* AI summary */}
      {!article.summarization_failed && article.summary && (
        <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
          {article.summary}
        </p>
      )}

      {/* Topics + sentiment */}
      {(article.topics.length > 0 || article.sentiment) && (
        <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
          {article.topics.slice(0, 3).map((topic) => (
            <span
              key={topic}
              className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
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
    <div className="flex flex-col items-center gap-3 py-10 px-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <Newspaper
          className="h-6 w-6 text-muted-foreground"
          aria-hidden="true"
        />
      </div>
      <div>
        <p className="text-sm font-medium text-foreground">No articles found</p>
        <p className="text-xs text-muted-foreground mt-1">
          No recent news coverage found for {ticker}.
        </p>
      </div>
    </div>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function NewsSummaryPanel() {
  const { news, ticker, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!news) return "loading";
    if (!news.available) return "unavailable";
    return "populated";
  })();

  const isLoading = !news && (status === "loading" || status === "streaming");
  const articleCount = news?.articles?.length ?? 0;

  const badge =
    news && news.available && articleCount > 0 ? (
      <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
        {articleCount}
      </span>
    ) : null;

  return (
    <Panel
      id="news_summary"
      title="Recent News"
      status={panelStatus}
      badge={badge}
    >
      {isLoading ? (
        <PanelSkeleton rows={5} />
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
