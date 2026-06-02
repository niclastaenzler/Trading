"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType } from "lightweight-charts";

type Candle = { time: number; open: number; high: number; low: number; close: number };

// Candlestick chart (TradingView Lightweight-Charts) for the live trading view.
export default function CandleChart({ data, height = 360 }: { data: Candle[]; height?: number }) {
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
        vertLines: { color: "#1c2333" },
        horzLines: { color: "#1c2333" },
      },
      rightPriceScale: { borderColor: "#232a3b" },
      timeScale: { borderColor: "#232a3b", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#2ecc71",
      downColor: "#e74c3c",
      borderUpColor: "#2ecc71",
      borderDownColor: "#e74c3c",
      wickUpColor: "#2ecc71",
      wickDownColor: "#e74c3c",
    });
    series.setData(data as any);
    chart.timeScale().fitContent();

    const onResize = () => chart.applyOptions({ width: ref.current?.clientWidth });
    onResize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, [data, height]);

  return <div ref={ref} style={{ width: "100%" }} />;
}
