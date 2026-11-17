import csv
import os
from datetime import datetime

import pygal
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

API_URL = "https://www.alphavantage.co/query"
API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
STOCKS_FILE = os.path.join(os.path.dirname(__file__), "stocks.csv")

TIME_SERIES = {
    "1": ("Intraday (60 min)", "TIME_SERIES_INTRADAY", "Time Series (60min)"),
    "2": ("Daily", "TIME_SERIES_DAILY", "Time Series (Daily)"),
    "3": ("Weekly", "TIME_SERIES_WEEKLY", "Weekly Time Series"),
    "4": ("Monthly", "TIME_SERIES_MONTHLY", "Monthly Time Series"),
}
CHART_TYPES = {"1": "Bar", "2": "Line"}


def load_symbols():
    """Read the stock symbols for the drop-down from stocks.csv."""
    try:
        with open(STOCKS_FILE, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            col = next((c for c in (reader.fieldnames or [])
                        if c.strip().lower() == "symbol"), None)
            if col is None:
                return [], "stocks.csv needs a 'Symbol' column."
            symbols = sorted({row[col].strip().upper() for row in reader
                              if row.get(col) and row[col].strip()})
            return symbols, None
    except FileNotFoundError:
        return [], "stocks.csv was not found. Add it next to app.py."
    except (OSError, csv.Error) as exc:
        return [], f"Could not read stocks.csv: {exc}"


def fetch_data(symbol, series_key):
    """Return (rows, error). rows is a list of (date_string, ohlc dict)."""
    if not API_KEY:
        return None, "No Alpha Vantage API key is set (ALPHAVANTAGE_API_KEY)."
    _, function, data_key = TIME_SERIES[series_key]
    params = {"function": function, "symbol": symbol, "apikey": API_KEY}
    if function == "TIME_SERIES_INTRADAY":
        params.update(interval="60min", outputsize="full")
    elif function == "TIME_SERIES_DAILY":
        params["outputsize"] = "full"
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        return None, f"Could not reach Alpha Vantage: {exc}"
    except ValueError:
        return None, "Alpha Vantage returned an unreadable response."

    for key in ("Error Message", "Note", "Information"):
        if key in payload:
            return None, payload[key]
    if data_key not in payload:
        return None, "Alpha Vantage returned no data for that request."
    return payload[data_key], None


def parse_date(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def build_chart(symbol, series_key, chart_key, begin, end, raw):
    rows = []
    for stamp, vals in raw.items():
        day = datetime.strptime(stamp[:10], "%Y-%m-%d").date()
        if begin <= day <= end:
            try:
                rows.append((stamp, [float(vals[k]) for k in
                                     ("1. open", "2. high", "3. low", "4. close")]))
            except (KeyError, ValueError):
                continue
    if not rows:
        return None
    rows.sort(key=lambda r: r[0])

    chart = pygal.Bar(x_label_rotation=45) if CHART_TYPES[chart_key] == "Bar" \
        else pygal.Line(x_label_rotation=45)
    chart.title = f"{symbol} {TIME_SERIES[series_key][0]}: {begin} to {end}"
    chart.x_labels = [r[0] for r in rows]
    chart.add("Open", [r[1][0] for r in rows])
    chart.add("High", [r[1][1] for r in rows])
    chart.add("Low", [r[1][2] for r in rows])
    chart.add("Close", [r[1][3] for r in rows])
    return chart.render_data_uri()


@app.route("/", methods=["GET", "POST"])
def index():
    symbols, symbols_error = load_symbols()
    form = {"symbol": "", "series": "2", "chart": "2", "begin": "", "end": ""}
    chart_uri, error = None, symbols_error

    if request.method == "POST":
        form.update({k: request.form.get(k, "").strip() for k in form})
        begin, end = parse_date(form["begin"]), parse_date(form["end"])
        if form["symbol"] not in symbols:
            error = "Please choose a stock symbol from the list."
        elif form["series"] not in TIME_SERIES or form["chart"] not in CHART_TYPES:
            error = "Please choose a valid chart type and time series."
        elif not begin or not end:
            error = "Please enter both a begin and an end date."
        elif end < begin:
            error = "The end date cannot be before the begin date."
        else:
            raw, error = fetch_data(form["symbol"], form["series"])
            if raw is not None:
                chart_uri = build_chart(form["symbol"], form["series"],
                                        form["chart"], begin, end, raw)
                if chart_uri is None:
                    error = "No data was found in that date range."

    return render_template("index.html", symbols=symbols, form=form, error=error,
                           chart_uri=chart_uri, series=TIME_SERIES,
                           chart_types=CHART_TYPES)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
