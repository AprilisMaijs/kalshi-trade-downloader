"""Client for Kalshi's public market-data API (no API key required).

Kalshi partitions trade data: recent trades come from /markets/trades,
trades older than a moving cutoff (see /historical/cutoff) come from
/historical/trades. fetch_trades() queries both sides and merges them.

API docs: https://docs.kalshi.com/
"""

import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
PAGE_LIMIT = 1000
PAGE_DELAY_SECONDS = 0.15  # stay polite on the public rate limit
MAX_RETRIES = 5


class KalshiApiError(Exception):
    """Raised when the Kalshi API keeps failing after retries."""


def _parse_ts(value):
    """Accept a Unix timestamp or an ISO 8601 string; return Unix seconds."""
    if isinstance(value, (int, float)):
        return int(value)
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class KalshiClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                last_error = str(exc)
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {response.status_code}"
                else:
                    raise KalshiApiError(
                        f"Kalshi API error {response.status_code} for {path}: "
                        f"{response.text[:300]}"
                    )
            time.sleep(min(2 ** attempt, 30))
        raise KalshiApiError(f"Kalshi API unreachable ({last_error}) for {path}")

    def _paginate(self, path, params, list_key, max_items=None, on_progress=None):
        items = []
        cursor = None
        while True:
            page_params = dict(params)
            page_params["limit"] = min(PAGE_LIMIT, page_params.get("limit", PAGE_LIMIT))
            if cursor:
                page_params["cursor"] = cursor
            data = self._get(path, page_params)
            items.extend(data.get(list_key) or [])
            if on_progress:
                on_progress(len(items))
            cursor = data.get("cursor")
            if not cursor or (max_items and len(items) >= max_items):
                return items[:max_items] if max_items else items
            time.sleep(PAGE_DELAY_SECONDS)

    # ---- discovery -------------------------------------------------------

    def get_trades_cutoff(self):
        """Unix timestamp separating live trades from historical trades."""
        data = self._get("/historical/cutoff")
        return _parse_ts(data["trades_created_ts"])

    def get_markets(self, event_ticker=None, series_ticker=None, tickers=None,
                    status=None, max_items=2000):
        params = {}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
            params["mve_filter"] = "exclude"  # required alongside series_ticker
        if tickers:
            params["tickers"] = ",".join(tickers) if isinstance(tickers, (list, tuple)) else tickers
        if status:
            params["status"] = status
        markets = self._paginate("/markets", params, "markets", max_items=max_items)
        # Markets settled before the cutoff move to the historical archive,
        # which supports event_ticker/tickers filters but not series_ticker.
        if not markets and (event_ticker or tickers):
            archive_params = {k: v for k, v in params.items() if k != "status"}
            markets = self._paginate("/historical/markets", archive_params,
                                     "markets", max_items=max_items)
        return markets

    def get_series_markets(self, series_ticker, complete=False, max_items=500):
        """All markets in a series, newest first from the live API.

        With complete=True, pagination is unbounded and markets settled
        before the cutoff are pulled from the historical archive as well
        (which accepts series_ticker but rejects mve_filter).
        """
        params = {"series_ticker": series_ticker, "mve_filter": "exclude"}
        markets = self._paginate("/markets", params, "markets",
                                 max_items=None if complete else max_items)
        if complete:
            by_ticker = {m["ticker"]: m for m in markets}
            archived = self._paginate("/historical/markets",
                                      {"series_ticker": series_ticker},
                                      "markets", max_items=None)
            for market in archived:
                by_ticker.setdefault(market["ticker"], market)
            markets = sorted(by_ticker.values(),
                             key=lambda m: m.get("open_time") or "")
        return markets

    def get_events(self, status=None, max_items=1000):
        params = {"limit": 200}  # /events caps limit at 200
        if status:
            params["status"] = status
        return self._paginate("/events", params, "events", max_items=max_items)

    # ---- trades ----------------------------------------------------------

    def fetch_trades(self, ticker, start_ts, end_ts, on_progress=None):
        """All trades for `ticker` with start_ts <= created_time <= end_ts.

        Queries the historical and/or live endpoint depending on where the
        requested window falls relative to the cutoff, deduplicates on
        trade_id, and returns normalized dicts sorted by created_time.
        """
        try:
            cutoff = self.get_trades_cutoff()
        except (KalshiApiError, KeyError, ValueError):
            cutoff = None  # if the cutoff lookup fails, query both sides

        raw = []

        def progress(source):
            def _cb(count):
                if on_progress:
                    on_progress(source, len(raw) + count)
            return _cb

        window = {"ticker": ticker, "min_ts": int(start_ts), "max_ts": int(end_ts)}
        if cutoff is None or start_ts < cutoff:
            raw.extend(self._paginate("/historical/trades", window, "trades",
                                      on_progress=progress("archive")))
        if cutoff is None or end_ts >= cutoff:
            live = self._paginate("/markets/trades", window, "trades",
                                  on_progress=progress("recent"))
            raw.extend(live)

        seen = set()
        trades = []
        for trade in raw:
            trade_id = trade.get("trade_id")
            if trade_id in seen:
                continue
            seen.add(trade_id)
            trades.append(self._normalize(trade))
        trades.sort(key=lambda t: t["created_time"])
        return trades

    @staticmethod
    def _normalize(trade):
        count = _to_float(trade.get("count_fp"))
        if count is None:
            count = _to_float(trade.get("count"))
        yes_price = _to_float(trade.get("yes_price_dollars"))
        no_price = _to_float(trade.get("no_price_dollars"))
        return {
            "trade_id": trade.get("trade_id"),
            "ticker": trade.get("ticker"),
            "created_time": trade.get("created_time"),
            "count": count,
            "yes_price_dollars": yes_price,
            "no_price_dollars": no_price,
            "taker_outcome_side": trade.get("taker_outcome_side") or trade.get("taker_side"),
            "taker_book_side": trade.get("taker_book_side"),
            "is_block_trade": trade.get("is_block_trade"),
        }


def day_bounds_utc(start_date, end_date):
    """Unix timestamps for 00:00:00 UTC on start_date through 23:59:59 UTC on end_date."""
    start = datetime(start_date.year, start_date.month, start_date.day,
                     tzinfo=timezone.utc)
    end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59,
                   tzinfo=timezone.utc)
    return int(start.timestamp()), int(end.timestamp())
