import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-with-at-least-32-characters")

import app as api


class FakeDatabase:
    def __init__(self):
        self.users = []
        self.queries = []

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def cursor(self, cursor_factory=None):
        return FakeCursor(self.database)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class FakeCursor:
    def __init__(self, database):
        self.database = database
        self.result = None

    def execute(self, query, params=None):
        params = params or ()
        self.database.queries.append((query, params))
        if query.count("%s") != len(params):
            raise AssertionError(f"SQL parameters do not match: {query}")
        if "SELECT COUNT(*) AS user_count" in query:
            self.result = {"user_count": len(self.database.users)}
        elif "INSERT INTO app_users" in query:
            email, password_hash = params
            if any(user["email"] == email for user in self.database.users):
                self.result = None
            else:
                user = {
                    "id": len(self.database.users) + 1,
                    "email": email,
                    "password_hash": password_hash,
                }
                self.database.users.append(user)
                self.result = {"id": user["id"], "email": email}
        elif "SELECT id, email, password_hash FROM app_users" in query:
            self.result = next(
                (user for user in self.database.users if user["email"] == params[0]),
                None,
            )
        elif "FROM jcb_work WHERE owner_uid=%s" in query:
            self.result = {
                "today_revenue": 0,
                "today_hours": 0,
                "today_driver_earning": 0,
                "month_revenue": 0,
                "month_hours": 0,
                "month_driver_earning": 0,
                "year_revenue": 0,
                "year_hours": 0,
                "year_driver_earning": 0,
                "total_revenue": 0,
                "total_hours": 0,
                "total_driver_earning": 0,
            }
        elif "FROM expenses WHERE owner_uid=%s" in query:
            self.result = {
                "today_expenses": 0,
                "month_expenses": 0,
                "year_expenses": 0,
                "total_expenses": 0,
            }
        else:
            self.result = None

    def fetchone(self):
        return self.result

    def fetchall(self):
        return []

    @property
    def rowcount(self):
        return 1

    def close(self):
        pass


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.db_patch = patch.object(api, "get_db", self.database.connect)
        self.db_patch.start()
        api.app.config.update(TESTING=True)
        self.client = api.app.test_client()

    def tearDown(self):
        self.db_patch.stop()

    def register(self, email):
        return self.client.post(
            "/api/auth/register",
            json={"email": email, "password": "a-strong-password"},
        )

    def test_private_api_requires_a_valid_login(self):
        for endpoint in ("/api/drivers", "/api/work", "/api/expenses", "/api/dashboard"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 401)

        registration = self.register("owner@example.com")
        token = registration.get_json()["token"]
        response = self.client.get(
            "/api/drivers",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("WHERE owner_uid=%s", self.database.queries[-1][0])
        self.assertEqual(self.database.queries[-1][1][-1], "1")

    def test_accounts_are_distinct_and_duplicate_email_is_rejected(self):
        first = self.register("Owner@Example.com")
        second = self.register("another@example.com")
        duplicate = self.register("owner@example.com")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertNotEqual(
            first.get_json()["user"]["id"],
            second.get_json()["user"]["id"],
        )
        self.assertTrue(api.check_password_hash(
            self.database.users[0]["password_hash"],
            "a-strong-password",
        ))
        self.assertFalse(any("UPDATE drivers" in query for query, _ in self.database.queries))

        for result, expected_owner in ((first, "1"), (second, "2")):
            response = self.client.get(
                "/api/drivers",
                headers={"Authorization": f"Bearer {result.get_json()['token']}"},
            )
            self.assertEqual(response.status_code, 200)
            query, params = self.database.queries[-1]
            self.assertIn("FROM drivers WHERE owner_uid=%s", query)
            self.assertEqual(params[-1], expected_owner)

    def test_all_record_lists_and_dashboard_are_scoped_to_the_account(self):
        registration = self.register("owner@example.com")
        token = registration.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        start = len(self.database.queries)

        for endpoint in ("/api/work", "/api/expenses", "/api/dashboard"):
            response = self.client.get(endpoint, headers=headers)
            self.assertEqual(response.status_code, 200)

        queries = self.database.queries[start:]
        owner_queries = [
            (query, params)
            for query, params in queries
            if "owner_uid=%s" in query
        ]
        self.assertGreaterEqual(len(owner_queries), 5)
        for _, params in owner_queries:
            self.assertIn("1", params)

    def test_new_records_are_inserted_with_the_authenticated_owner_id(self):
        registration = self.register("owner@example.com")
        headers = {"Authorization": f"Bearer {registration.get_json()['token']}"}
        requests = (
            ("/api/drivers", {"name": "Driver"}),
            ("/api/work", {
                "work_date": "2026-10-14",
                "hours": 2,
                "rate_per_hour": 100,
            }),
            ("/api/expenses", {
                "expense_date": "2026-10-14",
                "expense_type": "Fuel",
                "amount": 50,
            }),
        )

        for endpoint, payload in requests:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json=payload, headers=headers)
                self.assertEqual(response.status_code, 201)
                query, params = self.database.queries[-1]
                self.assertIn("owner_uid", query)
                self.assertEqual(params[-1], "1")

    def test_login_checks_the_password_hash(self):
        self.register("owner@example.com")
        correct = self.client.post(
            "/api/auth/login",
            json={"email": "OWNER@example.com", "password": "a-strong-password"},
        )
        incorrect = self.client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "wrong-password"},
        )

        self.assertEqual(correct.status_code, 200)
        self.assertEqual(incorrect.status_code, 401)


if __name__ == "__main__":
    unittest.main()
