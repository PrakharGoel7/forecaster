# Prism application

Prism's product application is split into a FastAPI service in `api/` and a Next.js client in `frontend/`.

For the product overview, architecture, setup guide, and configuration reference, see the [root README](../README.md).

## API

```bash
uvicorn prism.api.main:app --reload --port 8000
```

## Frontend

```bash
cd prism/frontend
npm ci
npm run dev
```

The app runs at [http://localhost:3000](http://localhost:3000) and expects the API at [http://localhost:8000](http://localhost:8000) by default.
