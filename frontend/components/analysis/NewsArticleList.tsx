"use client";

import type { NewsCollection } from "@/types/report";
import { formatDateTime } from "@/lib/formatters";
import { ExternalLink } from "lucide-react";

function sentimentAccentBar(sentiment: string): string {
  const s = sentiment.toLowerCase();
  if (s === "positive") return "bg-emerald-500";
  if (s === "negative") return "bg-red-500";
  return "bg-amber-400";
}

export function NewsArticleList({ news }: { news: NewsCollection }) {
  if (!news.available || news.articles.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic px-5 pb-5">
        No news articles available.
      </p>
    );
  }

  return (
    <section aria-label="Recent news articles" className="px-5 pt-2 pb-5">
      <div className="divide-y divide-border/60">
        {news.articles.map((article) => (
          <article
            key={article.article_id}
            className="group py-4 first:pt-2 last:pb-0"
          >
            <div className="flex items-start gap-3">
              {/* Sentiment accent strip */}
              <div
                className={`mt-1.5 w-1 h-4 rounded-full shrink-0 ${sentimentAccentBar(article.sentiment)}`}
                aria-hidden="true"
              />

              <div className="flex-1 min-w-0">
                {/* Title row */}
                <div className="flex items-start gap-2">
                  <h3 className="text-sm font-semibold text-foreground leading-snug flex-1 group-hover:text-brand-500 transition-colors duration-150">
                    {article.title}
                  </h3>
                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-muted-foreground hover:text-brand-500 transition-colors mt-0.5"
                      aria-label={`Read full article: ${article.title}`}
                    >
                      <ExternalLink
                        className="h-3.5 w-3.5"
                        aria-hidden="true"
                      />
                    </a>
                  )}
                </div>

                {/* Meta row */}
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <span className="text-xs font-semibold text-foreground/80">
                    {article.source_name}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {formatDateTime(article.published_at)}
                  </span>
                  {article.deduplication_count &&
                    article.deduplication_count > 1 && (
                      <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">
                        {article.deduplication_count} sources
                      </span>
                    )}
                </div>

                {/* AI summary */}
                {article.summary && !article.summarization_failed && (
                  <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                    {article.summary}
                  </p>
                )}

                {/* Topics */}
                {article.topics.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {article.topics.map((t) => (
                      <span
                        key={t}
                        className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
