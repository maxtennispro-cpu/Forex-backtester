"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { SETUP_LABELS } from "@/lib/setup-labels";

const SCORE_THRESHOLDS = [0, 50, 70, 85];

export default function Filters() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const activeType = params.get("type") ?? "";
  const activeMin = Number(params.get("min") ?? 0);

  function apply(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  return (
    <>
      <div className="filters">
        <button
          className={`chip ${activeType === "" ? "on" : ""}`}
          onClick={() => apply("type", "")}
        >
          All types
        </button>
        {Object.entries(SETUP_LABELS).map(([value, label]) => (
          <button
            key={value}
            className={`chip ${activeType === value ? "on" : ""}`}
            onClick={() => apply("type", value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="filters">
        {SCORE_THRESHOLDS.map((t) => (
          <button
            key={t}
            className={`chip ${activeMin === t ? "on" : ""}`}
            onClick={() => apply("min", t ? String(t) : "")}
          >
            {t === 0 ? "Any score" : `Score ${t}+`}
          </button>
        ))}
      </div>
    </>
  );
}
