import re

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.context import current_request_id
from apps.core.middleware import RequestIdMiddleware


def run(headers=None):
    seen = {}

    def view(request):
        seen["context"] = current_request_id()
        seen["attribute"] = request.request_id
        return HttpResponse("ok")

    request = RequestFactory().get("/", headers=headers or {})
    response = RequestIdMiddleware(view)(request)
    return response, seen


def test_generates_a_request_id_visible_during_the_request_and_in_the_response():
    response, seen = run()
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])
    assert seen == {"context": response["X-Request-ID"], "attribute": response["X-Request-ID"]}
    assert current_request_id() == ""  # reset after the request


def test_propagates_a_valid_incoming_request_id():
    response, seen = run({"X-Request-ID": "frontend-42.a_b"})
    assert response["X-Request-ID"] == seen["context"] == "frontend-42.a_b"


@pytest.mark.parametrize("bad", ["x" * 65, "has spaces", "semi;colon", "<script>"])
def test_replaces_an_invalid_incoming_request_id(bad):
    response, _ = run({"X-Request-ID": bad})
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])


def test_is_installed_first():
    assert settings.MIDDLEWARE[0] == "apps.core.middleware.RequestIdMiddleware"
