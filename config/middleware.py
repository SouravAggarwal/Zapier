import logging
import threading
import uuid


_local = threading.local()


def get_request_id():
    """Return the request ID bound to the current thread, or None outside a request."""
    return getattr(_local, "request_id", None)


class RequestIDMiddleware:
    """Attach a UUID request ID to every request and echo it in the response header.

    Reads X-Request-ID from the incoming request if present (allows load-balancers
    or upstream services to propagate their own trace ID). Otherwise generates a
    fresh uuid4. Stores the ID in thread-local storage so RequestIDFilter can stamp
    it on every log record produced during the request without needing it passed
    explicitly through the call stack.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        _local.request_id = request_id
        request.request_id = request_id

        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


class RequestIDFilter(logging.Filter):
    """Inject the current request ID into every log record as %(request_id)s."""

    def filter(self, record):
        record.request_id = get_request_id() or "-"
        return True
