"""OpenAPI of the messaging API: every endpoint is typed (no generator warnings) and no choice set becomes a
shared enum component. Choice fields are documented as plain strings on purpose: names like `status`,
`channel` or `language` exist in other apps with other choices, and a shared `StatusEnum` would make
`spectacular --fail-on-warn` (and generated clients) collide."""

import pytest
from django.urls import include, path
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator

PATTERNS = [
    path("api/v1/messaging/", include("apps.messaging.urls")),
    path("api/v1/public/messaging/", include("apps.messaging.public_urls")),
]


@pytest.fixture
def schema():
    GENERATOR_STATS.reset()
    yield SchemaGenerator(patterns=PATTERNS).get_schema(request=None, public=True)
    GENERATOR_STATS.reset()


def test_the_messaging_api_generates_without_warnings_or_errors(schema):
    assert dict(GENERATOR_STATS._warn_cache) == {}
    assert dict(GENERATOR_STATS._error_cache) == {}


def test_no_choice_set_is_hoisted_to_a_shared_enum(schema):
    components = schema["components"].get("schemas", {})
    assert "Conversation" in components  # the staff API is part of the schema
    enums = sorted(name for name, component in components.items() if "enum" in component)
    assert enums == []


def test_every_staff_endpoint_is_documented(schema):
    paths = set(schema["paths"])
    assert {
        "/api/v1/messaging/conversations/",
        "/api/v1/messaging/conversations/{id}/",
        "/api/v1/messaging/conversations/{id}/messages/",
        "/api/v1/messaging/conversations/{id}/read/",
        "/api/v1/messaging/conversations/{id}/assign/",
        "/api/v1/messaging/conversations/{id}/close/",
        "/api/v1/messaging/conversations/{id}/reopen/",
        "/api/v1/messaging/conversations/unread-count/",
        "/api/v1/messaging/templates/",
        "/api/v1/messaging/templates/{id}/",
        "/api/v1/messaging/templates/preview/",
        "/api/v1/messaging/variables/",
        "/api/v1/messaging/lifecycle-rules/",
        "/api/v1/messaging/lifecycle-rules/{id}/",
        "/api/v1/messaging/send/",
        "/api/v1/messaging/simulator/whatsapp/inbound/",
        "/api/v1/messaging/simulator/whatsapp/thread/",
        "/api/v1/messaging/simulator/whatsapp/contacts/",
        "/api/v1/public/messaging/webhooks/whatsapp/",
    } <= paths
