# STOCK_ANALYSIS_MODULE

This project monitors stock prices and signals if price breaks the day's High or Low. It persists the HL values to `hl.json` so a restart won't lose them. Use the included GitHub Actions workflow to ping the backend periodically so Render Free doesn't sleep the service.

### Deploy
1. Push this repo to GitHub.
2. Add repository secret `BACKEND_URL` with your Render app URL.
3. Connect backend/ folder to Render as a Web Service (Python). Use the command in Procfile.
4. Deploy frontend as a static site (or serve via same backend using a static route).

Environment variables (optional):
- `STOCKS` — comma separated tickers (default `RELIANCE.NS,SBIN.NS`)
- `FETCH_HOUR` — hour in IST (default `10`)
- `FETCH_MINUTE` — minute in IST (default `30`)
- `POLL_SECONDS` — how often to poll live price (default `4`)