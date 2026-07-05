"""Streamlit UI for downloading Kalshi trade history as CSV.

Everything runs locally: this app calls Kalshi's public API directly from
the machine it runs on. Launch with run_mac.command / run_windows.bat, or:
    streamlit run app.py
"""

import re
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

from kalshi_client import KalshiClient, KalshiApiError, day_bounds_utc

st.set_page_config(page_title="Kalshi Trade Downloader", page_icon="📈",
                   layout="centered")


@st.cache_resource
def client():
    return KalshiClient()


@st.cache_data(ttl=600, show_spinner=False)
def load_events(status):
    return client().get_events(status=status or None, max_items=1000)


@st.cache_data(ttl=600, show_spinner=False)
def markets_for_event(event_ticker):
    return client().get_markets(event_ticker=event_ticker)


def candidates_from_input(text):
    """Ticker candidates from a kalshi.com URL or a raw ticker, best guess first."""
    text = text.strip()
    if "kalshi.com" not in text.lower():
        return [text.upper()]
    candidates = []
    fragment = re.search(r"#([\w.-]+)", text)
    if fragment:
        candidates.append(fragment.group(1).upper())
    path = re.sub(r"[#?].*$", "", text)
    segments = [s for s in path.split("/") if s]
    if "markets" in [s.lower() for s in segments]:
        idx = [s.lower() for s in segments].index("markets")
        candidates.extend(s.upper() for s in segments[idx + 1:])

    def specificity(candidate):
        # Event/market tickers contain '-' plus digits (KXNBAREB-26MAY08NYKPHI);
        # series tickers are dash-free (KXMUSKWEALTH); dashed words without
        # digits are URL slugs (elon-musk-net-worth) — try those last.
        if "-" in candidate and any(c.isdigit() for c in candidate):
            return 0
        if "-" not in candidate:
            return 1
        return 2

    unique = list(dict.fromkeys(candidates))
    unique.sort(key=specificity)
    return unique or [text.upper()]


def resolve_markets(text):
    """Try each candidate as market ticker, then event ticker, then series ticker."""
    api = client()
    for candidate in candidates_from_input(text):
        for lookup in (
            lambda c: api.get_markets(tickers=c),
            lambda c: api.get_markets(event_ticker=c),
            lambda c: api.get_markets(series_ticker=c, max_items=500),
        ):
            try:
                markets = lookup(candidate)
            except KalshiApiError:
                markets = []
            if markets:
                return markets
    return []


def market_label(market):
    title = market.get("title") or market.get("yes_sub_title") \
        or market.get("subtitle") or market.get("ticker")
    close = (market.get("close_time") or "")[:10]
    return f"{title}  ·  {market['ticker']}  ·  {market.get('status', '?')}  ·  closes {close}"


def pick_market():
    st.header("1 · Pick a market")
    tab_paste, tab_browse = st.tabs(["Paste a Kalshi link or ticker", "Browse events"])

    with tab_paste:
        st.caption("Open the market on kalshi.com, copy the address from your "
                   "browser, and paste it here. A ticker like "
                   "`KXBTC15M-26JUL050845-45` works too.")
        text = st.text_input("Kalshi link or ticker", key="paste_input",
                             placeholder="https://kalshi.com/markets/...")
        if text:
            with st.spinner("Looking up market..."):
                st.session_state.paste_markets = resolve_markets(text)
            if not st.session_state.paste_markets:
                st.error("Couldn't find a market for that input. Double-check the "
                         "link or ticker — or try the Browse tab.")
        markets = st.session_state.get("paste_markets") or []
        if markets:
            choice = st.selectbox("Market", markets, format_func=market_label,
                                  key="paste_choice")
            return choice

    with tab_browse:
        status = st.selectbox("Event status", ["open", "closed", "settled"],
                              key="browse_status")
        if st.button("Load events", key="load_events"):
            with st.spinner("Loading events (this can take a moment)..."):
                st.session_state.browse_events = load_events(status)
        events = st.session_state.get("browse_events") or []
        if events:
            st.caption(f"{len(events)} events loaded — type in the box to search.")
            event = st.selectbox(
                "Event", events, key="browse_event",
                format_func=lambda e: f"{e.get('title', e['event_ticker'])}  ·  {e['event_ticker']}")
            if event:
                markets = markets_for_event(event["event_ticker"])
                if not markets:
                    st.warning("No markets found for this event.")
                else:
                    return st.selectbox("Market", markets, format_func=market_label,
                                        key="browse_choice")
    return None


def pick_timeframe(market):
    st.header("2 · Pick a timeframe")
    st.caption("Dates are in UTC. The default range covers the market's whole life.")
    today = datetime.now(timezone.utc).date()
    open_default = today
    open_time = market.get("open_time")
    if open_time:
        open_default = datetime.fromisoformat(open_time.replace("Z", "+00:00")).date()
    close_default = today
    close_time = market.get("close_time")
    if close_time:
        close_default = min(
            today, datetime.fromisoformat(close_time.replace("Z", "+00:00")).date())
    col_from, col_to = st.columns(2)
    start = col_from.date_input("From", value=open_default, key="date_from")
    end = col_to.date_input("To", value=max(close_default, open_default), key="date_to")
    if start > end:
        st.error("The start date is after the end date.")
        return None
    return day_bounds_utc(start, end)


def fetch_section(market, bounds):
    st.header("3 · Fetch trades")
    ticker = market["ticker"]
    if st.button(f"Fetch trades for {ticker}", type="primary"):
        status_line = st.empty()
        progress_of = {"archive": 0, "recent": 0}

        def on_progress(source, count):
            progress_of[source] = count
            total = max(progress_of.values())
            status_line.info(f"Downloading... {total:,} trades so far "
                             f"({'older archive' if source == 'archive' else 'recent data'})")

        try:
            trades = client().fetch_trades(ticker, bounds[0], bounds[1],
                                           on_progress=on_progress)
        except KalshiApiError as exc:
            status_line.empty()
            st.error(f"Kalshi's API could not be reached. Check your internet "
                     f"connection and try again.\n\nDetails: {exc}")
            return
        status_line.empty()
        st.session_state.result = (ticker, bounds, pd.DataFrame(trades))

    result = st.session_state.get("result")
    if not result or result[0] != ticker or result[1] != bounds:
        return
    _, _, df = result
    if df.empty:
        st.warning("No trades were found in this timeframe. Try widening the "
                   "date range — some markets trade only near their close date.")
        return
    st.success(f"Got {len(df):,} trades from {df['created_time'].iloc[0][:10]} "
               f"to {df['created_time'].iloc[-1][:10]}.")
    st.dataframe(df.head(100), width="stretch")
    start_str = datetime.fromtimestamp(bounds[0], tz=timezone.utc).strftime("%Y%m%d")
    end_str = datetime.fromtimestamp(bounds[1], tz=timezone.utc).strftime("%Y%m%d")
    st.download_button(
        "⬇️ Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{ticker}_{start_str}_{end_str}.csv",
        mime="text/csv",
        type="primary",
    )


st.title("📈 Kalshi Trade Downloader")
st.caption("Downloads the full trade history of a Kalshi market as a CSV file. "
           "Runs entirely on this computer using Kalshi's public API.")

selected_market = pick_market()
if selected_market:
    st.divider()
    timeframe = pick_timeframe(selected_market)
    if timeframe:
        st.divider()
        fetch_section(selected_market, timeframe)
