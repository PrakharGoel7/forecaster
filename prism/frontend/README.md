# Prism web app

The Next.js client for Prism's social forecasting and prediction-market portfolio experience. It provides market discovery, AI and manual basket builders, community theses, creator profiles, authentication, and personalized feeds.

See the [repository README](../../README.md) for the full product overview and backend setup.

## Local development

```bash
cp .env.example .env.local
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | FastAPI base URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase browser client key |

## Checks

```bash
npm run lint
npm run build
```
