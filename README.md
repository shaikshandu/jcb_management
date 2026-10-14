# JCB Management

A simple JCB work and expense tracker.

## What this project uses

- `frontend/` - React website built with Vite
- `backend/` - Python API built with Flask
- PostgreSQL - database for drivers, work records, and expenses

The website sends requests to the Python API. The API reads and writes data in PostgreSQL.

## Run it on your computer

### 1. Create a PostgreSQL database

Install PostgreSQL, then create a database named `jcb_management` using pgAdmin or the PostgreSQL command line:

```sql
CREATE DATABASE jcb_management;
```

### 2. Configure and start the backend

From the project folder, copy the example settings and move into the backend folder:

```powershell
Copy-Item backend\.env.example backend\.env
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Open `backend/.env` in your editor and set:

- `DATABASE_URL` to your local PostgreSQL connection string.
- `SECRET_KEY` to a new random secret of at least 32 characters. In PowerShell, generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.

Keep this file private; never commit or share it.

Start the API:

```powershell
python app.py
```

The API runs at <http://127.0.0.1:5000>.

### 3. Start the React website

Open a second terminal in the project folder, move into `frontend/`, install the JavaScript packages, and start Vite:

```powershell
cd frontend
npm install
npm run dev
```

Open the local website address printed by Vite (usually <http://localhost:5173>). During local development, Vite forwards `/api` requests to the Flask API.

## Deploy it

Deploy the frontend and backend separately:

1. Create a hosted PostgreSQL database, for example on Render.
2. Deploy `backend/` as a Python web service on Render. Set the root directory to `backend`, the build command to `pip install -r requirements.txt`, and the start command below. Add `DATABASE_URL` with the hosted PostgreSQL connection string and `SECRET_KEY` with a new random secret generated as above. The backend will not start without a valid `SECRET_KEY`. After deploying the website, set `FRONTEND_ORIGINS` to its exact public origin.

   ```text
   python -c "from app import init_db; init_db()" && gunicorn app:app
   ```

3. Deploy `frontend/` on Vercel. Set the root directory to `frontend`, the build command to `npm run build`, and the output directory to `dist`.
4. In Vercel, set `VITE_API_BASE_URL` to the public backend URL, without a trailing slash, then redeploy.
5. Set the backend's `FRONTEND_ORIGINS` to the Vercel website URL and redeploy the backend.

The backend root URL returns a small API status message. The user-facing website is the Vercel URL.

## Accounts and private data

Each person creates an account with an email address and a password of at least 10 characters. Passwords are stored as secure hashes, not plain text. Every API request requires a signed, expiring login token, and database queries are scoped to the signed-in account. Existing deployments must redeploy the backend so its startup command creates the account table and updates the tables.

Older records that have no owner are deliberately not assigned automatically, so a new public signup cannot accidentally see them. If those old records belong to your account, first create your account, then use pgAdmin to find its ID:

```sql
SELECT id, email FROM app_users;
```

Replace `YOUR_ACCOUNT_ID` below with the ID for your own email. Run this only if all old unowned records belong to you:

```sql
BEGIN;
UPDATE drivers SET owner_uid = 'YOUR_ACCOUNT_ID' WHERE owner_uid IS NULL;
UPDATE jcb_work SET owner_uid = 'YOUR_ACCOUNT_ID' WHERE owner_uid IS NULL;
UPDATE expenses SET owner_uid = 'YOUR_ACCOUNT_ID' WHERE owner_uid IS NULL;
COMMIT;
```

Use a unique, strong password and keep the `SECRET_KEY` private. Signing out clears the login token from the current browser session. A lost or stolen token remains valid until it expires, so keep the website dependencies and deployment settings up to date.
