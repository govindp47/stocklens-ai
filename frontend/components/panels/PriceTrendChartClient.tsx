'use client';

/**
 * PriceTrendChartClient — Recharts line chart rendered client-side only.
 *
 * This component is imported via next/dynamic({ ssr: false }) in
 * PriceTrendChart.tsx to prevent SSR hydration errors from Recharts.
 */

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import type { PricePoint } from '@/types/report';

interface PriceTrendChartClientProps {
  datapoints: PricePoint[];
}

export default function PriceTrendChartClient({
  datapoints,
}: PriceTrendChartClientProps) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart
        data={datapoints}
        margin={{ top: 4, right: 8, bottom: 4, left: 8 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: string) => {
            // Show abbreviated month/day — e.g. "Nov 1"
            try {
              const d = new Date(`${v}T00:00:00`);
              return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            } catch {
              return v;
            }
          }}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={['auto', 'auto']}
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) =>
            new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              minimumFractionDigits: 0,
              maximumFractionDigits: 0,
            }).format(v)
          }
          width={52}
        />
        <Tooltip
          contentStyle={{ fontSize: 11, borderRadius: 4, border: '1px solid #e5e7eb' }}
          formatter={(value: number) =>
            new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              minimumFractionDigits: 2,
            }).format(value)
          }
        />
        <Line
          type="monotone"
          dataKey="close"
          stroke="hsl(210 100% 50%)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
