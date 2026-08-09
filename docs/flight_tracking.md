# Flight Tracker provider foundation

Flight Tracker is manual-only in this release. Creating, editing, pausing, archiving, and restoring a tracker is entirely local. A **Check now** request makes no network request unless a locally configured provider is available.

## Provider boundary

`app.flight_provider.FlightProvider` is the small provider interface. It receives only the route, dates, passenger count, cabin class, and currency needed for a search, and returns normalized offers. It does not receive journal, notes, tasks, attachments, or other application data.

The initial adapter is for the documented Amadeus Flight Offers Search API. It is intentionally dormant by default and does not contain an API key, secret, demo fare, or fallback scraping behaviour. Its current API shape supports conventional return trips only; an open-jaw tracker is retained locally and produces a clear, safe check failure until a compatible adapter is added.

## Local configuration

Only configure a provider when you already have legitimate credentials and permission to use it. Keep values in your ignored local configuration or environment; never commit them.

```text
FLIGHT_PROVIDER=amadeus
AMADEUS_CLIENT_ID=your_local_client_id
AMADEUS_CLIENT_SECRET=your_local_client_secret
```

When those values are absent, the interface states **Flight provider not configured** and checks remain local. The app does not create provider accounts, initiate billing, schedule background checks, send email, scrape websites, or use Google as a data source.

## Stored data and interpretation

Each completed manual check records the provider name, timestamp, search configuration version, outcome, and normalized matching offers. Price is stored as integer cents and quality classification uses duration and stop limits; price is not used as a quality rule. The lowest price is only a comparison summary. A route, date, or cabin change begins a new configuration version while preserving prior observations for history.

Provider errors are reduced to safe, actionable messages. Credentials, request headers, raw payloads, and URLs containing secrets are not displayed or logged by this feature. Booking links are retained only when a provider supplies a valid HTTPS link; the initial adapter does not invent one.
