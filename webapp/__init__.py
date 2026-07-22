"""Subscription web app wrapped around the forex backtester.

A small FastAPI site in the style of retail trading-signal services:
marketing landing page, subscription plans/pricing page, user accounts,
and a members' dashboard whose gated content is real output from
``forex_backtester`` (run on synthetic candles so no OANDA key is needed).
"""
