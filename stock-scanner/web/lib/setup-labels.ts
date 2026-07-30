/**
 * Setup type labels, importable from client components.
 *
 * `lib/supabase.ts` is server-only (it holds the service key), so the
 * label map lives here where both sides can use it.
 */
export const SETUP_LABELS = {
  breakout: "Breakout",
  volume_spike: "Volume spike",
  momentum: "Momentum",
  oversold_bounce: "Oversold bounce",
} as const;

export type SetupType = keyof typeof SETUP_LABELS;
