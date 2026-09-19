"""The exit dataset is rate-limited upstream (data.gov.sg answers 429 after a
couple of calls), so it must be fetched once per process, not once per client."""

import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from clients.lta_datamall_client import LtaDataMallClient

FEATURE = {"properties": {"STATION_NA": "HOUGANG MRT STATION", "EXIT_CODE": "Exit A"}, "geometry": {"coordinates": [103.89, 1.37]}}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("rate limited", request=httpx.Request("GET", "https://x"), response=httpx.Response(self.status_code))

    def json(self):
        return self._payload


class FakeAsyncClient:
    calls = 0
    status = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        FakeAsyncClient.calls += 1
        return FakeResponse({"type": "FeatureCollection", "features": [FEATURE]}, FakeAsyncClient.status)


class TestStationExitCache(unittest.TestCase):
    def setUp(self):
        LtaDataMallClient._exit_cache = []
        LtaDataMallClient._exit_cache_until = datetime.min.replace(tzinfo=timezone.utc)
        FakeAsyncClient.calls, FakeAsyncClient.status = 0, 200
        patcher = patch("clients.lta_datamall_client.httpx.AsyncClient", FakeAsyncClient)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, LtaDataMallClient, "_exit_cache_until", datetime.min.replace(tzinfo=timezone.utc))
        self.addCleanup(setattr, LtaDataMallClient, "_exit_cache", [])

    def test_exits_fetched_once_across_client_instances(self):
        first = asyncio.run(LtaDataMallClient().station_exits())
        second = asyncio.run(LtaDataMallClient().station_exits())
        self.assertEqual(len(first), 1)
        self.assertEqual(second, first)
        self.assertEqual(FakeAsyncClient.calls, 1, "each request builds new clients; the cache must be shared")

    def test_backs_off_after_rate_limit(self):
        FakeAsyncClient.status = 429
        self.assertEqual(asyncio.run(LtaDataMallClient().station_exits()), [])
        self.assertEqual(asyncio.run(LtaDataMallClient().station_exits()), [])
        self.assertEqual(FakeAsyncClient.calls, 1, "a rate-limited dataset must not be re-requested on every call")

    def test_stale_exits_served_when_upstream_rate_limits(self):
        cached = asyncio.run(LtaDataMallClient().station_exits())
        LtaDataMallClient._exit_cache_until = datetime.min.replace(tzinfo=timezone.utc)
        FakeAsyncClient.status = 429
        self.assertEqual(asyncio.run(LtaDataMallClient().station_exits()), cached)


if __name__ == "__main__":
    unittest.main()
