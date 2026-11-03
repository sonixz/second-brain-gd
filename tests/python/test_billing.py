import datetime as dt
import io
import json
import unittest
import urllib.error
from unittest import mock

from engine import billing

NOW = dt.datetime(2026, 11, 3, 15, 0, tzinfo=dt.timezone.utc)


def page(buckets, has_more=False, next_page=None):
    return {"object": "page", "data": buckets, "has_more": has_more, "next_page": next_page}


def bucket(day: str, results):
    t0 = int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())
    return {"object": "bucket", "start_time": t0, "end_time": t0 + 86400, "results": results}


def cost(value, item):
    return {"object": "organization.costs.result", "amount": {"value": value, "currency": "usd"}, "line_item": item}


class FetchBillingTests(unittest.TestCase):
    def test_fake_pages_aggregate(self):
        d = billing.fetch_billing(billing.fake_fetch(), 30, NOW)
        self.assertEqual(len(d["days"]), 30)
        self.assertEqual(d["days"][-1]["day"], "2026-11-03")
        self.assertEqual(d["month_start"], "2026-11-01")
        # input and output of one model are one product on the chart
        self.assertIn("gpt-4o-2024-08-06", d["groups"])
        self.assertNotIn("gpt-4o-2024-08-06, input", d["groups"])
        self.assertAlmostEqual(d["today"], d["days"][-1]["cost"], places=6)
        self.assertAlmostEqual(d["month"], sum(x["cost"] for x in d["days"][-3:]), places=6)
        self.assertGreater(d["period"], d["month"])
        tok = d["tokens"]
        self.assertEqual(tok["requests"], sum(m["requests"] for m in d["models"]))
        self.assertTrue(any(m["model"] == "gpt-realtime-whisper" and m["seconds"] == 120 for m in d["models"]))

    def test_costs_are_exactly_what_openai_says_and_pages_are_followed(self):
        calls = []

        def fetch(path, params):
            calls.append((path, dict(params)))
            if path != "/costs":
                return page([])
            if "page" not in params:
                return page([bucket("2026-11-02", [cost(1.25, "gpt-4o, input")])], True, "p2")
            return page([bucket("2026-11-03", [cost(0.5, "gpt-4o, output"), cost(0.25, "gpt-6-astra, output")])])

        d = billing.fetch_billing(fetch, 7, NOW)
        self.assertEqual(d["month"], 2.0)
        self.assertEqual(d["today"], 0.75)
        self.assertEqual(d["line_items"][0], {"name": "gpt-4o, input", "cost": 1.25})
        self.assertEqual([c[1].get("page") for c in calls if c[0] == "/costs"], [None, "p2"])
        self.assertEqual(calls[0][1]["group_by"], ["line_item"])
        self.assertEqual(calls[0][1]["bucket_width"], "1d")

    def test_many_products_fold_into_other(self):
        items = [cost(1.0 + i, f"model-{i}, input") for i in range(8)]
        d = billing.fetch_billing(lambda p, q: page([bucket("2026-11-03", items)] if p == "/costs" else []), 7, NOW)
        self.assertEqual(len(d["groups"]), billing.MAX_GROUPS + 1)
        self.assertEqual(d["groups"][-1], "Other")
        self.assertEqual(d["groups"][0], "model-7")  # ranked by spend
        self.assertAlmostEqual(sum(d["days"][-1]["by_group"].values()), sum(1.0 + i for i in range(8)))

    def test_forbidden_key_is_explained(self):
        err = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"{}"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(billing.BillingError) as ctx:
                billing.fetch_billing(billing.http_fetch("sk-proj-x"), 7, NOW)
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("admin key", str(ctx.exception))
        self.assertNotIn("sk-proj-x", str(ctx.exception))

    def test_request_shape(self):
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(req, timeout=0):
            seen["url"], seen["auth"] = req.full_url, req.headers.get("Authorization")
            return Resp(json.dumps(page([])).encode())

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            billing.http_fetch("sk-admin-test")("/costs", {"start_time": 1, "group_by": ["line_item"]})
        self.assertTrue(seen["url"].startswith("https://api.openai.com/v1/organization/costs?"))
        self.assertIn("group_by=line_item", seen["url"])
        self.assertEqual(seen["auth"], "Bearer sk-admin-test")


class CacheTests(unittest.TestCase):
    def test_not_configured_without_key(self):
        with mock.patch.dict("os.environ", {"SBGD_BILLING_PROVIDER": ""}):
            out = billing.Billing(lambda: None).get()
        self.assertFalse(out["configured"])

    def test_cache_until_refresh(self):
        b = billing.Billing(lambda: None)
        with mock.patch.dict("os.environ", {"SBGD_BILLING_PROVIDER": "fake"}):
            first = b.get(30)
            self.assertFalse(first["cached"])
            self.assertTrue(b.get(30)["cached"])
            self.assertFalse(b.get(30, refresh=True)["cached"])


if __name__ == "__main__":
    unittest.main()
