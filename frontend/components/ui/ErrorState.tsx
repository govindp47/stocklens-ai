/**
 * ErrorState — shown inside a panel when its data step completely failed.
 *
 * Accessibility:
 * - role="alert" causes screen readers to announce the error immediately.
 * - Icon is aria-hidden="true" — the message text is the accessible label.
 */

import { AlertCircle } from 'lucide-react';

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="p-4 flex flex-col items-center gap-2 text-center"
      data-testid="error-state"
    >
      <AlertCircle
        className="w-6 h-6 text-sentiment-negative"
        aria-hidden="true"
      />
      <p className="text-sm text-neutral-600">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs text-brand-500 underline min-h-[44px] min-w-[44px] px-2"
        >
          Try again
        </button>
      )}
    </div>
  );
}
