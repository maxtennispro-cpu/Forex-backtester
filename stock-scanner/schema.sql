-- Supabase schema for the AI stock scanner.
-- Run this once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query).

create table if not exists watchlist (
    ticker     text primary key,
    added_at   timestamptz not null default now()
);

create table if not exists setups (
    id             bigint generated always as identity primary key,
    scan_date      date not null,
    ticker         text not null,
    setup_type     text not null,          -- breakout | volume_spike | momentum | oversold_bounce
    close          double precision not null,
    volume         bigint not null,
    indicators     jsonb not null,         -- raw indicator values at scan time
    closes         jsonb not null,         -- last ~60 daily closes for the mini chart
    ai_score       integer,                -- 1-100, filled by the scoring pass
    ai_rationale   text,
    ai_invalidation text,
    fwd_5d         double precision,       -- % change 5 trading days after scan (backfilled)
    fwd_10d        double precision,
    fwd_20d        double precision,
    created_at     timestamptz not null default now(),
    unique (scan_date, ticker, setup_type)
);

create index if not exists setups_scan_date_idx on setups (scan_date desc);
create index if not exists setups_outcome_idx on setups (scan_date) where fwd_20d is null;

-- The app talks to Supabase with the service-role key from the server only,
-- so RLS is enabled with no public policies: anon access is fully locked out.
alter table watchlist enable row level security;
alter table setups enable row level security;
