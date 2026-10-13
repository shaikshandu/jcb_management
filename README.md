# JCB Management System

A JCB daily work, driver earnings, expenses, and revenue management system.

## Stack

- Frontend: React, Vite, CSS
- Backend: Python Flask
- Database: PostgreSQL
- Authentication: Firebase Authentication with Google sign-in
- Charts: Chart.js

## Features

- Dashboard with revenue, hours, driver earnings, expenses, and profit
- Daily JCB work, drivers, and expenses
- Work and expense history, monthly/yearly summary, and driver earnings
- Google account login with PostgreSQL data isolated by verified Firebase account

## 1. Create the PostgreSQL database

In pgAdmin or PostgreSQL terminal, run:

```sql
CREATE DATABASE jcb_management;
```

## 2. Configure PostgreSQL and Firebase Admin

Copy `backend/.env.example` to `backend/.env` and set the PostgreSQL connection. In Firebase Console:

1. Create/select a Firebase project, add a Web app, and enable **Authentication → Sign-in method → Google**. Select a support email if Firebase asks for one.
2. Add `localhost` to Authentication's authorized domains for local development.
3. Create a Firebase Admin service-account key. Store its JSON file somewhere private outside the project folder and set `FIREBASE_ADMIN_CREDENTIALS` in `backend/.env` to its absolute path. Never commit or share this file.

For example on Windows:

```dotenv
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/jcb_management
FIREBASE_ADMIN_CREDENTIALS=C:\secure\firebase-service-account.json
```

Google sign-in does not send verification SMS. Firebase Authentication validates the Google identity, and the backend only accepts tokens with a verified email from the Google sign-in provider.

## 3. Install Python packages

From `backend`:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Configure and build the React frontend

Copy `frontend/.env.example` to `frontend/.env.local` and set the Firebase Web app API key, Auth domain, project ID, and App ID. These browser settings are not the Admin service-account key. Restrict the Web API key to your app's domains in Google Cloud.

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

For frontend development, keep Flask running, then from `frontend` run `npm run dev` and open the URL Vite prints. API calls are proxied to Flask. Add each development/production web domain to Firebase Authentication's authorized domains. Rebuild with `npm run build` before using the Flask-hosted page.

Users sign in with Google. Firebase preserves the sign-in across page reloads. Flask verifies the Firebase ID token, verified email, and Google provider identity on API requests. This also supports an existing phone account after Google has been linked to it, preserving its Firebase UID and PostgreSQL records.

If this browser has records from the older browser-only version, the page offers to copy them into the currently signed-in Google account once. Accept only if those local records belong to that account; the browser copy is retained. Existing PostgreSQL rows created before account ownership have no owner and remain hidden until an administrator assigns them to the correct account. When a browser has an older phone-auth session, the Google button links Google to that Firebase account so its UID and records stay the same. If the Google account is already attached to a different Firebase UID, Firebase cannot merge those accounts automatically; after signing in with Google, an administrator can inspect the account IDs in pgAdmin:

```sql
SELECT firebase_uid, email, phone_number
FROM user_accounts
ORDER BY created_at;
```

To transfer records from the old phone account, first verify the old phone account and the new Google account belong to the same person. Replace the two UID placeholders with the exact IDs from the query above, then run this transaction in pgAdmin:

```sql
BEGIN;
UPDATE drivers SET owner_uid = 'GOOGLE_FIREBASE_UID' WHERE owner_uid = 'OLD_PHONE_FIREBASE_UID';
UPDATE jcb_work SET owner_uid = 'GOOGLE_FIREBASE_UID' WHERE owner_uid = 'OLD_PHONE_FIREBASE_UID';
UPDATE expenses SET owner_uid = 'GOOGLE_FIREBASE_UID' WHERE owner_uid = 'OLD_PHONE_FIREBASE_UID';
COMMIT;
```

Transfer only after confirming both IDs; assigning data to the wrong account exposes private business records. Rows whose `owner_uid` is still `NULL` are pre-ownership legacy data and require a separate, carefully verified assignment.

In pgAdmin, inspect the account-owned work history with:

```sql
SELECT ua.email, ua.phone_number, w.*
FROM jcb_work w
JOIN user_accounts ua ON ua.firebase_uid = w.owner_uid
ORDER BY w.work_date DESC, w.id DESC;
```

Protect the database and Firebase Admin key, use HTTPS for public hosting, and back up PostgreSQL regularly with `pg_dump`. The Flask development server listens only on this computer.

## Project structure

```text
jcb_management/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   └── .env.example
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
