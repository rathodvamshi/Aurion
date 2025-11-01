# Deploy frontend (Vercel) + backend (Render)

This guide gets your React frontend live on Vercel and the FastAPI backend on Render, with CORS and envs wired for smooth communication.

## Overview
- Frontend: `frontend/` (Create React App) → Vercel static site
- Backend: `backend/` (FastAPI/Uvicorn) → Render Web Service
- API base URL is configured via environment variable so all environments (dev/preview/prod) stay in sync.

## 1) Backend on Render

We included a `render.yaml` at the repo root. In Render:

1. Create a New Web Service → “Build & deploy from a Git repository” → choose this repo.
2. Render will auto-detect `render.yaml`. Confirm the service named `aurion-backend`.
3. The service uses:
   - Root dir: `backend`
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/` (does not depend on DB/Redis)
4. Set all required environment variables in Render → Settings → Environment:

Required secrets (must have real values):
- SECRET_KEY (generated automatically by render.yaml first deploy; regenerate if needed)
- MONGO_URI (MongoDB Atlas connection string)
- MONGO_DB (e.g., MAYA)
- MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM (for email/OTP; if not set, email endpoints will be disabled)
- PINECONE_API_KEY (for embeddings)
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (Neo4j Aura)

Recommended/optional:
- REDIS_URL (Redis Cloud URL, e.g., `rediss://:PASSWORD@HOST:6380/0`)
- GEMINI_API_KEY, OPENAI_API_KEY (AI providers)
- NEWS_API_KEY, WEATHER_API_KEY (aux services)
- APP_VERSION (any string for /api/info)

CORS settings (pick one strategy):
- Safer (recommended): set `CORS_ORIGINS` to your final frontend URL(s), e.g.
  - `https://your-app.vercel.app`
  - multiple origins allowed via comma: `https://your-app.vercel.app,https://www.yourdomain.com`
- For Vercel preview URLs: set `CORS_ALLOW_VERCEL_PREVIEWS=true` so `*.vercel.app` is accepted.
- During early testing only, you can temporarily set `CORS_ALLOW_ALL=true` (don’t leave this on in production).

Save changes and deploy. After successful deploy, note the backend URL, e.g., `https://aurion-backend.onrender.com`.

## 2) Frontend on Vercel (Create React App)

1. In Vercel → New Project → Import your repo or connect `frontend/` as the root directory when prompted.
   - If Vercel doesn’t prompt for subdirectory, set “Root Directory” to `frontend/` in project settings.
2. Build settings
   - Framework preset: “Other” (CRA is static)
   - Install command: `npm ci --legacy-peer-deps` (already in `frontend/vercel.json`)
   - Build command: `npm run build`
   - Output directory: `build`
3. Environment variables (project → Settings → Environment Variables):
   - REACT_APP_API_URL = https://aurion-backend.onrender.com
   - Optionally:
     - REACT_APP_REALTIME_TRANSPORT = off (or `sse` if you later enable SSE and auth)
     - Any other `REACT_APP_*` your app references
4. Redeploy. Your Vercel site will be, e.g., `https://your-app.vercel.app`.

## 3) Verify end-to-end

- Open: `https://aurion-backend.onrender.com/api/info` → should return JSON with version/origins
- Open: `https://your-app.vercel.app` and try login/register and a simple API call
- If you see CORS errors, confirm on Render:
  - `CORS_ORIGINS` contains your Vercel domain (exact origin) or
  - `CORS_ALLOW_VERCEL_PREVIEWS=true` if using preview URLs

## 4) Environment management (dev/preview/prod)

Render (backend):
- Use Render “Environment” to manage variables per service. Keep secrets there—no commits.
- For Preview deploys (PRs), Render creates preview services. Either:
  - set `CORS_ALLOW_VERCEL_PREVIEWS=true` to accept `*.vercel.app`, or
  - update `CORS_ORIGINS` to include each preview domain (manual).

Vercel (frontend):
- Add env vars in all three tabs as needed: Development, Preview, Production.
  - Development: usually `http://localhost:8000`
  - Preview: the preview Render URL (if you deploy preview backends) or production backend
  - Production: your Render production URL
- In CRA, only vars prefixed with `REACT_APP_` are exposed to the client.

Local development:
- `frontend/.env.local` already supports `REACT_APP_API_URL=http://127.0.0.1:8000`
- Backend CORS already includes `http://localhost:3000` by default; you don’t need to set CORS_ORIGINS locally.

## 5) Common gotchas

- 500 at startup on Render: missing required envs in backend (see list above). Add them and redeploy.
- CORS blocked in browser:
  - Ensure Vercel domain is in `CORS_ORIGINS` on Render, or set `CORS_ALLOW_VERCEL_PREVIEWS=true`.
  - Don’t include trailing slashes in origins.
- Mixed `/api` base duplication:
  - The frontend normalizes `REACT_APP_API_URL` and appends `/api` exactly once. Provide the backend origin (no trailing slash, no `/api`).
- Health checks failing:
  - Render health check path is `/`; it doesn’t require DB/Redis.
- Emails not working:
  - Configure `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`. Without them, `/test-email` will return 503.

## 6) Optional hardening

- Disable dynamic dev origins and previews in prod: set `CORS_ALLOW_VERCEL_PREVIEWS=false` and keep exact origins in `CORS_ORIGINS`.
- Set `DB_INMEMORY_FALLBACK=0` to avoid accidental writes being accepted when Mongo is down.
- Set `REQUEST_LOG_SAMPLE=0.2` to sample request logs at 20% volume.

## 7) Quick checklist

- [ ] Render backend deployed and exposes a URL
- [ ] Render env has required secrets set
- [ ] Vercel frontend deployed with REACT_APP_API_URL pointing to Render
- [ ] CORS adjusted (origins or previews enabled)
- [ ] Basic flows tested: register/login, simple API call, `/api/info`
