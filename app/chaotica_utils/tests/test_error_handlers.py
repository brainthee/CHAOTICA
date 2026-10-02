"""Error handlers reset stale DB connections (Sentry CHAOTICA-103/-11D/-13N etc.).

Under ASGI, error pages render in a thread pool outside the per-request
connection cleanup, so a MySQL-timed-out connection was reused and every such
404/500 raised ``(2006, 'Server has gone away')``.
"""
from unittest import mock

from django.test import Client, SimpleTestCase, TestCase
from django.urls import get_resolver

from chaotica_utils.views import errors


class _FakeConn:
    def __init__(self, in_atomic_block):
        self.in_atomic_block = in_atomic_block
        self.close_if_unusable_or_obsolete = mock.Mock()


class ErrorHandlerConnectionTests(SimpleTestCase):
    def _call(self, conns):
        handler = mock.Mock(return_value="response")
        wrapped = errors._with_fresh_db(handler)
        with mock.patch.object(errors.connections, "all", return_value=conns):
            result = wrapped("request", exception=None)
        handler.assert_called_once_with("request", exception=None)
        return result

    def test_stale_connection_released_before_and_after(self):
        conn = _FakeConn(in_atomic_block=False)
        self.assertEqual(self._call([conn]), "response")
        self.assertEqual(conn.close_if_unusable_or_obsolete.call_count, 2)

    def test_connection_in_transaction_left_alone(self):
        conn = _FakeConn(in_atomic_block=True)
        self._call([conn])
        conn.close_if_unusable_or_obsolete.assert_not_called()

    def test_released_even_when_handler_raises(self):
        conn = _FakeConn(in_atomic_block=False)
        wrapped = errors._with_fresh_db(mock.Mock(side_effect=RuntimeError))
        with mock.patch.object(errors.connections, "all", return_value=[conn]):
            with self.assertRaises(RuntimeError):
                wrapped("request")
        self.assertEqual(conn.close_if_unusable_or_obsolete.call_count, 2)

    def test_handlers_registered(self):
        resolver = get_resolver()
        for code, name in [
            (400, "bad_request"), (403, "permission_denied"),
            (404, "page_not_found"), (500, "server_error"),
        ]:
            handler = resolver.resolve_error_handler(code)
            self.assertIs(handler, getattr(errors, name), code)


class NotFoundPageTests(TestCase):
    def test_unknown_url_renders_404_inside_test_transaction(self):
        resp = Client(HTTP_HOST="localhost").get("/definitely/not/a/page/")
        self.assertEqual(resp.status_code, 404)
