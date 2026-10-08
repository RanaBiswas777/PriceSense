# PriceSense

PriceSense is a local-first product price-history and smart purchase assistant.
It stores observed prices, calculates transparent historical statistics in
Python, and can use a local Qwen model to explain those statistics. Users can
set a target price and explicitly check the latest stored observation for a
target crossing.

## What it does

- Loads the deterministic offline demo product at `sample://demo-001`.
- Persists products and price observations in a local SQLite database.
- Reports current, lowest, highest, average, and median prices; recent average;
  trend; price position; and a rule-based price classification.
- Optionally explains compact, analytics-derived evidence using Qwen3:4B
  through a separately running local Ollama service.
- Keeps Python's deterministic classification authoritative and displays a
  deterministic explanation if the AI provider is unavailable or returns an
  invalid response.
- Supports target-price tracking, explicit stored-price checks, crossing-based
  alert history, and tracking deactivation.

## Architecture

```text
Streamlit Analyze UI
  ├── Product service → ProductDataAdapter → SampleAdapter or recognized
  │   but unavailable marketplace placeholder → repositories → SQLite
  ├── Analytics service → deterministic Python price statistics
  │                         └── compact evidence → AI assessment service
  │                                                   └── Ollama → Qwen3:4B
  └── Tracking / alert services → repositories → SQLite
```

The UI delegates product, analytics, AI, and tracking work to their respective
layers. Qwen only explains structured evidence; it does not calculate prices,
classify them, or predict future prices.

## Technology stack

- Python 3.11+
- Streamlit
- SQLite and SQLAlchemy
- Plotly
- python-dotenv
- pytest
- Ollama with Qwen3:4B (optional at runtime; the application remains usable
  when Ollama is unavailable)

## Project structure

```text
PriceSense/
├── ai/                 # Evidence schema, prompts, assessment service, Ollama provider
├── analytics/          # Deterministic price statistics and database-backed service
├── collectors/         # Adapter contract, offline sample adapter, marketplace placeholders
├── data/               # Bundled sample CSV and local SQLite database
├── database/           # SQLite initialization, ORM models, repositories
├── services/           # Product resolution, target tracking, alert evaluation
├── tests/              # Unit, Streamlit, database, and end-to-end integration tests
├── ui/                 # Streamlit Analyze page
├── app.py              # Streamlit entry point
├── config.py           # Centralized environment configuration
├── requirements.txt
└── .env.example
```

## Setup (Windows PowerShell)

From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

The defaults in `.env.example` are safe local settings and require no
credentials. Edit `.env` only if you need to change the database filename or
local Ollama settings. `.env` is excluded by `.gitignore`; do not commit it.
Never put API keys, passwords, tokens, or other credentials in source code or
in the example file.

### Optional local AI setup

1. Install Ollama using its official instructions and ensure the Ollama service
   is running separately from PriceSense.
2. Make the `qwen3:4b` model available to Ollama (for example, with
   `ollama pull qwen3:4b`).
3. Confirm the defaults in `.env` or configure:

   ```dotenv
   AI_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen3:4b
   OLLAMA_TIMEOUT_SECONDS=60
   ```

PriceSense does not start or stop Ollama. If it is offline, the dashboard keeps
showing deterministic analytics and labels the Python-generated explanation as
a fallback.

## Run the application

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address printed by Streamlit. Enter `sample://demo-001` and
select **Analyze** for the offline walkthrough.

## Demo data and marketplace limitations

The bundled `data/sample_prices.csv` is synthetic SAMPLE / DEMO DATA. The page
labels it clearly; it is not a live Amazon or Flipkart price. The sample
adapter is deterministic, works offline, and is never used to fill in for a
failed live-source request.

No permitted, configured live marketplace source is available in this build.
Amazon and Flipkart URLs are recognized only to show a clear unavailable-source
message. PriceSense does not scrape marketplace pages or bypass CAPTCHA,
authentication, bot protection, rate limits, paywalls, robots restrictions, or
other marketplace access controls.

## Analytics, AI, tracking, and alerts

All statistics and LOW / AVERAGE / HIGH / INSUFFICIENT_DATA classifications
are computed by Python from stored observations. Qwen receives compact
structured evidence, not the full raw price history, and cannot override the
Python classification. Its output is validated; a status mismatch receives
one correction attempt, then uses the deterministic fallback.

By default, a classification requires at least three valid observations.
Python compares the current price with the historical average: at least 10%
below is LOW, at least 10% above is HIGH, and values between those thresholds
are AVERAGE. Too few observations or a zero-width historical range produces
INSUFFICIENT_DATA. The thresholds and observation minimum can be changed with
the documented analytics variables in `.env.example`.

Tracking accepts a positive target price and displays the latest stored price,
target difference, and reached/not-reached state. Select **Check stored price**
to evaluate the latest observation. An alert is recorded when the price first
reaches or falls below the target. Repeated checks in that crossing do not
duplicate the alert; a later above-target observation resets the crossing, so
a subsequent drop can create a new alert. History is retained in SQLite.

Checks are explicit and local. There is no background scheduler, email/SMS
delivery, live price refresh, or guarantee that a future price will decrease.

## Tests

Run the complete suite from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

The suite covers database persistence, adapter and product resolution,
deterministic analytics and edge cases, Ollama protocol handling with mocked
HTTP responses, AI validation and fallback, Streamlit behavior, tracking and
crossing-based alerts, and the sample end-to-end flow. Tests use temporary
databases and do not require marketplace credentials or a running Ollama
service.

## Security and limitations

- Configuration is loaded from environment variables and the optional,
  gitignored `.env`; `.env.example` contains defaults only.
- The local SQLite database is not encrypted. Protect the machine and local
  project files according to your needs.
- No authentication, live marketplace integration, scheduled checks, or
  external alert delivery is implemented.
- No access-control circumvention or prohibited scraping is performed.
