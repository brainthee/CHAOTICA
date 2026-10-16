"""WebSocket handshakes from other sites are refused (cross-site WS hijack)."""

import asyncio

from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, override_settings

from chaotica_utils.ws_auth import WsAuthMiddleware, origin_allowed


def _scope(origin=None, host="chaotica.example.com", forwarded_host=None):
    headers = [(b"host", host.encode())]
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    if forwarded_host:
        headers.append((b"x-forwarded-host", forwarded_host.encode()))
    return {"type": "websocket", "headers": headers}


class OriginAllowedTests(SimpleTestCase):
    def test_same_host_allowed(self):
        self.assertTrue(origin_allowed(_scope("https://chaotica.example.com")))

    def test_port_difference_ignored(self):
        # nginx forwards $host (no port) while the browser Origin keeps it.
        self.assertTrue(
            origin_allowed(_scope("http://localhost:1338", host="localhost"))
        )

    def test_foreign_origin_refused(self):
        self.assertFalse(origin_allowed(_scope("https://evil.example.net")))

    def test_lookalike_origin_refused(self):
        self.assertFalse(
            origin_allowed(_scope("https://chaotica.example.com.evil.net"))
        )

    def test_null_origin_refused(self):
        self.assertFalse(origin_allowed(_scope("null")))

    def test_missing_origin_allowed(self):
        self.assertTrue(origin_allowed(_scope(None)))

    def test_forwarded_host_matches(self):
        self.assertTrue(
            origin_allowed(
                _scope("https://chaotica.example.com", host="web:8000",
                       forwarded_host="chaotica.example.com")
            )
        )

    @override_settings(CSRF_TRUSTED_ORIGINS=["https://ops.example.org"])
    def test_trusted_origin_allowed(self):
        self.assertTrue(origin_allowed(_scope("https://ops.example.org")))


class WsAuthMiddlewareTests(SimpleTestCase):
    def _connect(self, origin):
        reached = []

        async def inner(scope, receive, send):
            reached.append(True)
            await receive()
            await send({"type": "websocket.accept"})

        async def run():
            comm = WebsocketCommunicator(
                WsAuthMiddleware(inner),
                "/ws/schedule/global/",
                headers=[(b"host", b"chaotica.example.com"), (b"origin", origin.encode())],
            )
            connected, _ = await comm.connect()
            await comm.disconnect()
            return connected

        return asyncio.run(run()), bool(reached)

    def test_foreign_origin_never_reaches_consumer(self):
        connected, reached = self._connect("https://evil.example.net")
        self.assertFalse(connected)
        self.assertFalse(reached)

    def test_same_origin_reaches_consumer(self):
        connected, reached = self._connect("https://chaotica.example.com")
        self.assertTrue(connected)
        self.assertTrue(reached)
