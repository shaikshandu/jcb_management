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

Open `backend/.env` in your editor and set `DATABASE_URL` to your local PostgreSQL connection string. Keep this file private; never commit or share it.

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
2. Deploy `backend/` as a Python web service on Render. Set the root directory to `backend`, the build command to `pip install -r requirements.txt`, and the start command below. Add `DATABASE_URL` with the hosted PostgreSQL connection string. After deploying the website, set `FRONTEND_ORIGINS` to its exact public origin.

   ```text
   python -c "from app import init_db; init_db()" && gunicorn app:app
   ```

3. Deploy `frontend/` on Vercel. Set the root directory to `frontend`, the build command to `npm run build`, and the output directory to `dist`.
4. In Vercel, set `VITE_API_BASE_URL` to the public backend URL, without a trailing slash, then redeploy.
5. Set the backend's `FRONTEND_ORIGINS` to the Vercel website URL and redeploy the backend.

The backend root URL returns a small API status message. The user-facing website is the Vercel URL.

## Important security note

The current login is only a demo check in frontend JavaScript; it does not protect the API or database records. Use fake data only on a public deployment until proper authentication and authorization are added to the backend.
