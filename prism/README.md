# Prism — Next.js frontend

## Start the API

```bash
cd prism/api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Credentials are read automatically from `../forecaster/.env`.

## Start the frontend

```bash
cd prism/frontend
npm run dev
```

App → http://localhost:3000  
API → http://localhost:8000
