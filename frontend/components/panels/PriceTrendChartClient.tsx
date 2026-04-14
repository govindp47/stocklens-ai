"use client";

/**
 * PriceTrendChartClient — Recharts line chart rendered client-side only.
 *
 * This component is imported via next/dynamic({ ssr: false }) in
 * PriceTrendChart.tsx to prevent SSR hydration errors from Recharts.
 *
 * Uses CSS variables for all colors so it is fully theme-aware in
 * both light and dark modes.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import type { PricePoint } from "@/types/report";
import { useEffect, useRef, useState } from "react";

interface PriceTrendChartClientProps {
  datapoints: PricePoint[];
}

export default function PriceTrendChartClient({
  datapoints,
}: PriceTrendChartClientProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width && height) {
        setSize({ width, height });
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const cleanData = datapoints
    .filter((d) => typeof d.close === "number" && !isNaN(d.close))
    .map((d) => ({
      ...d,
      close: Number(d.close),
    }))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  const prices = cleanData.map((d) => d.close as number);

  let min = prices.length ? Math.min(...prices) : 0;
  let max = prices.length ? Math.max(...prices) : 1;

  let range = max - min;
  if (range < 0.5) {
    const center = (max + min) / 2;
    min = center - 1;
    max = center + 1;
    range = max - min;
  }

  const padding = range * 0.2;
  const yDomain: [number, number] = [min - padding, max + padding];

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%" }}>
      {size.width > 0 && size.height > 0 && (
        <LineChart
          width={size.width}
          height={size.height}
          data={cleanData}
          margin={{ top: 4, right: 8, bottom: 4, left: 8 }}
        >
          <CartesianGrid
            strokeDasharray="2 4"
            vertical={false}
            stroke="hsl(var(--border))"
            strokeOpacity={0.6}
          />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={true}
            axisLine={true}
            tickFormatter={(v: string) => {
              try {
                const d = new Date(`${v}T00:00:00`);
                return d.toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                });
              } catch {
                return v;
              }
            }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={yDomain}
            scale="linear"
            dataKey="close"
            type="number"
            tickCount={5}
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={false}
            allowDataOverflow={false}
            interval="preserveStartEnd"
          />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid hsl(var(--border))",
              background: "hsl(var(--surface))",
              color: "hsl(var(--foreground))",
              boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
            }}
            labelStyle={{ color: "hsl(var(--muted-foreground))", fontSize: 10 }}
          />
          <Line
            type="monotoneX"
            dataKey="close"
            stroke="hsl(var(--brand-500))"
            strokeWidth={2}
            dot={false}
            activeDot={{
              r: 4,
              fill: "hsl(var(--brand-500))",
              stroke: "hsl(var(--surface))",
              strokeWidth: 2,
            }}
            isAnimationActive={true}
            animationDuration={600}
          />
          <ReferenceLine
            y={prices[0]}
            stroke="hsl(var(--muted-foreground))"
            strokeDasharray="3 3"
          />
        </LineChart>
      )}
    </div>
  );
}
