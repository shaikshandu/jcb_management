# JCB Management System

A JCB daily work, driver earnings, expenses, and revenue management system.

## Stack

- Frontend: React, Vite, CSS
- Backend: Python Flask
- Database: PostgreSQL
- Authentication: demo passcode in the frontend (not production authentication)
- Charts: Chart.js

## Features

- Dashboard with revenue, hours, driver earnings, expenses, and profit
- Daily JCB work, drivers, and expenses
- Work and expense history, monthly/yearly summary, and driver earnings
- Passcode-gated demo interface

## 1. Create the PostgreSQL database

In pgAdmin or PostgreSQL terminal, run:

```sql
CREATE DATABASE jcb_management;
```

## 2. Configure PostgreSQL

Copy `backend/.env.example` to `backend/.env` and set `DATABASE_URL` to your PostgreSQL connection string. The backend creates its tables when started with `python app.py`.

For example on Windows:

```dotenv
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/jcb_management
```

## 3. Install Python packages

From `backend`:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Configure and build the React frontend

Copy `frontend/.env.example` to `frontend/.env.local`. Leave `VITE_API_BASE_URL` empty for local development; Vite proxies `/api` requests to Flask.

From `frontend`:

```bash
npm install
npm run build
```

## 5. Start the application

From `backend`:

```bash
python app.py
```

Open <http://127.0.0.1:5000>.

For frontend development, keep Flask running, then from `frontend` run `npm run dev` and open the URL Vite prints. API calls are proxied to Flask. Rebuild with `npm run build` before using the Flask-hosted page.

## 6. Deploy the frontend to Netlify

The repository includes `netlify.toml`; Netlify builds the Vite app from `frontend` and publishes `frontend/dist`. Connect this repository to Netlify and keep the detected settings, or use:

- Base directory: `frontend`
- Build command: `npm run build`
- Publish directory: `dist`

The Flask API and PostgreSQL database cannot run as part of this static Netlify deployment. Deploy them separately on a host that supports Python and PostgreSQL, then configure:

1. In Netlify, add the `VITE_API_BASE_URL` environment variable with the public backend origin, for example `https://your-backend.example.com` (no trailing slash), and redeploy.
2. In the backend host, set `DATABASE_URL` to the hosted PostgreSQL connection string and `FRONTEND_ORIGINS` to your Netlify site origin, for example `https://your-site.netlify.app`.
3. Run the backend with a production WSGI server and HTTPS. Do not expose the Flask development server to the internet.

**Do not use this demo with real or sensitive data on a public site.** The password check is performed in frontend JavaScript, and the Flask API currently has no authentication or per-user data isolation. The Firebase client file is not connected to the running login/API flow. Add real authentication and enforce authorization in the backend before public use.

Back up PostgreSQL regularly with `pg_dump`.

## Project structure

```text
jcb_management/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   └── .env.example
├── netlify.toml
├── frontend/
│   ├── index.html
│   ├── .env.example
│   ├── src/
│   │   ├── firebaseClient.js
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── style.css
└── README.md
```
