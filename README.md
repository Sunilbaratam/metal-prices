# Gold & Silver Prices (India): GitHub Actions + GitHub Pages

No server. A scheduled GitHub job fetches prices once a day and publishes the website.

```
every day 10:00 IST
  GitHub Actions  ->  GoldAPI (2 requests)
                  ->  saves data/prices.db in this repo   (history + request counter live here)
                  ->  exports latest.json + history_*.json
                  ->  builds the React site and deploys it to GitHub Pages
```

## One-time setup

Do these in this order. If you push before steps 2 and 3, the first run fails.

1. **Get a fresh GoldAPI key.** Don't reuse one that was ever pasted in a chat.
2. **Create the repository** on GitHub (for example `gold-prices`). Free GitHub Pages needs a **public** repo.
   Then in the repo: **Settings > Secrets and variables > Actions > New repository secret**
   - Name: `GOLDAPI_KEY`, Value: your key.
3. **Turn on Pages:** Settings > Pages > Source: **GitHub Actions**.
4. **Put your database in place.** Copy your local `backend/prices.db` (the one with the imported history)
   to `data/prices.db` in this folder. Without it the first run fails with "No prices in the database yet".
5. **Push:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo>.git
   git push -u origin main
   ```
   Check `git status` first: `.env` must not be listed.
6. Open the **Actions** tab. The first run (triggered by the push) builds and deploys the site using your existing
   data. **It makes no GoldAPI calls.** Your site is at `https://<your-username>.github.io/<repo>/`.
7. **Test a real refresh once:** Actions > "Daily prices and deploy" > **Run workflow**. This spends 2 requests.

From then on it runs by itself every day at 10:00 IST.

## When import duty or GST changes

Open `.github/workflows/daily.yml`, edit the `DUTY_SCHEDULE` (and `GST_PCT`) lines, and push. The push re-exports and
redeploys with the new rates. It does not call GoldAPI.

```yaml
DUTY_SCHEDULE: "2000-01-01:6,2026-05-13:15,2027-02-01:12"   # add new entries at the end
```

## Other settings (same file)

| Setting | What it does |
|---|---|
| `cron: "30 4 * * *"` | Run time in UTC. 04:30 UTC is 10:00 IST. Keep it to once a day on the free GoldAPI plan. |
| `MONTHLY_REQUEST_BUDGET` | The job stops fetching if the logged requests this month would exceed this. |
| `STALE_AFTER_HOURS` | The site shows an "out of date" warning when prices are older than this. |

## Preview on your computer

```bash
cd backend
source .venv/bin/activate
DB_PATH=../data/prices.db python scripts/daily_job.py      # export only, no GoldAPI call
cd ../frontend
npm install
npm run dev                                                # http://localhost:5173
```

## Things to know

- **The database is committed to the repo.** Each daily run adds a small commit ("Update prices"). That is how the
  history and request counter persist. Don't delete `data/prices.db`.
- **Public repo means public data.** Anyone can download your price history and the saved GoldAPI responses.
  Your key is not stored there. If that is a concern, use Cloudflare Pages or Netlify with a private repo instead.
- **If a run fails** (for example GoldAPI is down or the monthly budget is used), the site is still deployed with the
  last known prices and GitHub marks the run red and emails you. Prices show a warning once they pass `STALE_AFTER_HOURS`.
- **Scheduled runs can start a few minutes late.** GitHub may also pause scheduled workflows in a repo with no activity
  for a long time. If that happens, re-enable it in the Actions tab.
- **Old action versions.** If GitHub warns that an action version (for example `actions/checkout@v4`) is outdated,
  raise the version number in `daily.yml`.
- **Backfilling history or changing the schema** is still done locally with `backend/scripts/import_history.py` and
  `fetch_history.py`, then commit the updated `data/prices.db`.
