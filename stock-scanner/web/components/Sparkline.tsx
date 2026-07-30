"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

/**
 * Mini price chart for a setup card: the last ~60 daily closes. Colored by
 * net direction over the window, with a light tooltip for reading values.
 */
export default function Sparkline({ closes }: { closes: number[] }) {
  if (!closes || closes.length < 2) return null;

  const data = closes.map((close, i) => ({ i, close }));
  const rising = closes[closes.length - 1] >= closes[0];
  const stroke = rising ? "#2ecc8f" : "#ff6b6b";
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  const pad = (hi - lo) * 0.08 || hi * 0.01;

  return (
    <div className="spark">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
          <YAxis hide domain={[lo - pad, hi + pad]} />
          <Tooltip
            contentStyle={{
              background: "#1b2230",
              border: "1px solid #26303f",
              borderRadius: 8,
              fontSize: 12,
              padding: "4px 8px",
            }}
            labelFormatter={(i) => `${closes.length - Number(i)}d ago`}
            formatter={(value) => [`$${Number(value).toFixed(2)}`, "Close"]}
          />
          <Line
            type="monotone"
            dataKey="close"
            stroke={stroke}
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
