/**
 * StatusIndicator — maps panel status to a color + icon pair.
 *
 * Icons are aria-hidden — the status is conveyed via the parent Panel's name.
 */

import {
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  MinusCircle,
} from "lucide-react";
import type { PanelStatus } from "./Panel";

interface StatusIndicatorProps {
  status: PanelStatus;
}

const STATUS_CONFIG: Record<
  PanelStatus,
  {
    Icon: React.FC<React.SVGProps<SVGSVGElement>>;
    className: string;
    label: string;
  }
> = {
  loading: {
    Icon: Loader2 as React.FC<React.SVGProps<SVGSVGElement>>,
    className: "text-muted-foreground animate-spin",
    label: "Loading",
  },
  populated: {
    Icon: CheckCircle2 as React.FC<React.SVGProps<SVGSVGElement>>,
    className: "text-sentiment-positive",
    label: "Data loaded",
  },
  partial: {
    Icon: AlertTriangle as React.FC<React.SVGProps<SVGSVGElement>>,
    className: "text-amber-500",
    label: "Partial data",
  },
  error: {
    Icon: XCircle as React.FC<React.SVGProps<SVGSVGElement>>,
    className: "text-sentiment-negative",
    label: "Error",
  },
  unavailable: {
    Icon: MinusCircle as React.FC<React.SVGProps<SVGSVGElement>>,
    className: "text-muted-foreground",
    label: "Unavailable",
  },
};

export function StatusIndicator({ status }: StatusIndicatorProps) {
  const { Icon, className, label } = STATUS_CONFIG[status];

  return (
    <span title={label}>
      <Icon className={`h-3.5 w-3.5 ${className}`} aria-hidden="true" />
    </span>
  );
}
