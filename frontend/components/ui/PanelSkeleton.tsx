/**
 * PanelSkeleton — shimmer loading placeholder shown inside a panel
 * while its data is being fetched.
 *
 * Accessibility:
 * - aria-busy="true" signals to assistive technology that content is loading.
 * - aria-label provides a text alternative for the animation.
 */

interface PanelSkeletonProps {
  rows?: number;
  /** Show a larger "hero" block before the rows (for price panels etc.) */
  hero?: boolean;
}

export function PanelSkeleton({ rows = 4, hero = false }: PanelSkeletonProps) {
  const widths = ["88%", "72%", "80%", "64%", "84%", "60%"];

  return (
    <div
      className="p-5 space-y-3.5"
      aria-busy="true"
      aria-label="Loading data"
      data-testid="panel-skeleton"
    >
      {hero && (
        <div className="flex items-end gap-4 mb-5">
          <div className="h-10 w-40 rounded-xl animate-shimmer" />
          <div className="h-6 w-20 rounded-full animate-shimmer" />
        </div>
      )}
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-3.5 rounded-full animate-shimmer"
          style={{ width: widths[i % widths.length] }}
        />
      ))}
    </div>
  );
}
