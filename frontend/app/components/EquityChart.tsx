"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType } from "lightweight-charts";

// Renders a numeric series as a TradingView Lightweight-Charts line.
// `data` is a plain array of values (e.g. an equity curve); the x-axis uses a
// synthetic hourly timeline so it renders without per-point timestamps.
export default function EquityChart({
  data,
  height = 260,
  color = "#4c8bf5",
}: {
  data: number[];
  height?: number;
  color?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || !data?.length) return;

    const chart = createChart(ref.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8b93a7",
      },
      grid: {
        vertLines: { color: "#232a3b" },
        horzLines: { color: "#232a3b" },
      },
      rightPriceScale: { borderColor: "#232a3b" },
      timeScale: { borderColor: "#232a3b", timeVisible: false },
      handleScroll: false,
      handleScale: false,
    });

    const series = chart.addLineSeries({ color, lineWidth: 2 });
    const base = Math.floor(Date.now() / 1000) - data.length * 3600;
    series.setData(
      data.map((value, i) => ({ time: (base + i * 3600) as any, value }))
    );
    chart.timeScale().fitContent();

    const onResize = () =>
      chart.applyOptions({ width: ref.current?.clientWidth });
    onResize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, [data, height, color]);

  return <div ref={ref} style={{ width: "100%" }} />;
}
