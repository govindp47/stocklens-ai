/**
 * StatusIndicator — maps panel status to a color + icon pair.
 *
 * Accessibility:
 * - Icons are aria-hidden="true" — the status is conveyed to screen readers
 *   via the parent Panel's accessible name, not this component.
 * - Never relies on color alone; each status has a distinct icon shape.
 */

import {
  Loader2,
  CheckCircle,
  AlertTriangle,
  XCircle,
  MinusCircle,
} from 'lucide-react';
import type { PanelStatus } from './Panel';

interface StatusIndicatorProps {
  status: PanelStatus;
}

const STATUS_CONFIG: Record<
  PanelStatus,
  { Icon: React.FC<React.SVGProps<SVGSVGElement>>; className: string; label: string }
> = {
  loading: {
    Icon: Loader2 as React.FC<React.SVGProps<SVGSVGElement>>,
    className: 'text-neutral-400 animate-spin',
    label: 'Loading',
  },
  populated: {
    Icon: CheckCircle as React.FC<React.SVGProps<SVGSVGElement>>,
    className: 'text-sentiment-positive',
    label: 'Data loaded',
  },
  partial: {
    Icon: AlertTriangle as React.FC<React.SVGProps<SVGSVGElement>>,
    className: 'text-amber-500',
    label: 'Partial data',
  },
  error: {
    Icon: XCircle as React.FC<React.SVGProps<SVGSVGElement>>,
    className: 'text-sentiment-negative',
    label: 'Error',
  },
  unavailable: {
    Icon: MinusCircle as React.FC<React.SVGProps<SVGSVGElement>>,
    className: 'text-neutral-400',
    label: 'Unavailable',
  },
};

export function StatusIndicator({ status }: StatusIndicatorProps) {
  const { Icon, className, label } = STATUS_CONFIG[status];

  return (
    // Wrap in a span with a visually-hidden label so the status is
    // available to screen readers without being read twice.
    <span title={label}>
      <Icon
        className={`w-4 h-4 ${className}`}
        aria-hidden="true"
      />
    </span>
  );
}
