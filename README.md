# Kalshi Trade Downloader

A small app that downloads the **complete trade history of any Kalshi
prediction market** as a CSV file, for a chosen date range. It runs entirely
on your own computer and talks directly to [Kalshi's public
API](https://docs.kalshi.com/) — no account, API key, or server needed.

Built for academic research: the CSV opens directly in Excel, R, Stata,
SPSS, or Python/pandas.

## Setup (one time, ~5 minutes)

1. **Install Python** (version 3.10 or newer) from
   [python.org/downloads](https://www.python.org/downloads/).
   - **Windows:** on the first installer screen, tick **"Add python.exe to
     PATH"** before clicking Install.
   - **Mac:** just run the installer with the default options.
2. **Download this app:** click the green **Code** button at the top of this
   page → **Download ZIP**, then unzip it somewhere convenient (e.g. your
   Desktop).

That's it — the app installs its own components automatically the first time
you start it.

## Starting the app

- **Mac:** double-click **`run_mac.command`**.
  - If macOS says the file "cannot be opened", right-click it and choose
    **Open**, then confirm. (Only needed the first time.)
  - If double-clicking opens it as text instead, open the Terminal app, type
    `bash `, drag the file into the window, and press Enter.
- **Windows:** double-click **`run_windows.bat`**. If Windows shows a blue
  "protected your PC" screen, click **More info → Run anyway**.

The first start takes a minute while it sets itself up. Then a browser tab
opens with the app. Keep the black terminal window open while you work;
close it when you're done.

## Using the app

1. **Pick a market.** The easiest way: find the market on
   [kalshi.com](https://kalshi.com), copy the web address from your browser,
   and paste it into the app. You can also browse events by status.
   - If the link points to a whole **event or series** (several related
     markets), you can choose **"All markets"** to download every one of
     them into a single CSV — the `ticker` column tells the rows apart.
   - For recurring series (daily temperatures, hourly Bitcoin prices, ...)
     the lookup normally shows the 500 newest markets. Tick **"Load the
     complete series"** to list every market the series has ever had —
     listing and downloading a large series can take a long time.
2. **Pick a timeframe.** Two date pickers; the default covers the market's
   entire life. All times are UTC.
3. **Fetch & download.** Click the fetch button, watch the progress, preview
   the data, and click **Download CSV**.

Note: Kalshi keeps recent trades and older trades in two separate archives.
The app checks both automatically, so you always get the complete history.

## What's in the CSV

| Column | Meaning |
|---|---|
| `trade_id` | Unique identifier of the trade |
| `ticker` | Market ticker the trade happened in |
| `created_time` | When the trade executed (UTC, ISO 8601) |
| `count` | Number of contracts traded |
| `yes_price_dollars` | Price paid per YES contract, in US dollars (0–1) |
| `no_price_dollars` | Price paid per NO contract, in US dollars (0–1) |
| `taker_outcome_side` | Which side the aggressing (taker) order was on: `yes` or `no` |
| `taker_book_side` | Whether the taker hit the `bid` or the `ask` |
| `is_block_trade` | `True` if the trade was negotiated off the order book |

## Data source & citation

All data comes from Kalshi's public trade API
(`https://api.elections.kalshi.com/trade-api/v2`), specifically the
[`GET /markets/trades`](https://docs.kalshi.com/api-reference/market/get-trades)
and
[`GET /historical/trades`](https://docs.kalshi.com/api-reference/historical/get-historical-trades)
endpoints. See [docs.kalshi.com](https://docs.kalshi.com/) for the official
documentation — useful for a methodology section.

## For developers

```bash
pip install -r requirements.txt
streamlit run app.py
```

The API logic lives in `kalshi_client.py` (plain Python, no Streamlit) and
can be imported directly in scripts or notebooks:

```python
from kalshi_client import KalshiClient
trades = KalshiClient().fetch_trades("SOME-TICKER", start_ts, end_ts)
```

## License

MIT — see [LICENSE](LICENSE).
