/**
 * ErrorState — shown inside a panel when its data step completely failed.
 *
 * Accessibility:
 * - role="alert" causes screen readers to announce the error immediately.
 * - Icon is aria-hidden="true" — the message text is the accessible label.
 */

import { AlertCircle } from "lucide-react";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="p-6 flex flex-col items-center gap-3 text-center"
      data-testid="error-state"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-50 dark:bg-red-950/30">
        <AlertCircle
          className="w-5 h-5 text-sentiment-negative"
          aria-hidden="true"
        />
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed max-w-xs">
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs font-medium text-brand-500 hover:text-brand-600 underline underline-offset-2 min-h-[44px] min-w-[44px] px-2 transition-colors"
        >
          Try again
        </button>
      )}
    </div>
  );
}
