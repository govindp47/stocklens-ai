/**
 * PanelSkeleton — animated loading placeholder shown inside a panel
 * while its data is being fetched.
 *
 * Accessibility:
 * - aria-busy="true" signals to assistive technology that content is loading.
 * - aria-label provides a text alternative for the animation.
 */

interface PanelSkeletonProps {
  rows?: number;
}

export function PanelSkeleton({ rows = 3 }: PanelSkeletonProps) {
  return (
    <div
      className="p-4 space-y-3"
      aria-busy="true"
      aria-label="Loading data"
      data-testid="panel-skeleton"
    >
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 bg-neutral-100 rounded animate-pulse"
          style={{ width: `${70 + (i % 3) * 10}%` }}
        />
      ))}
    </div>
  );
}
