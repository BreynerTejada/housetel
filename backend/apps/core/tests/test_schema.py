import pytest


@pytest.mark.django_db
def test_openapi_schema_generates_and_lists_the_auth_endpoints(public_api):
    response = public_api.get("/api/schema/?format=json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/v1/accounts/auth/csrf/",
        "/api/v1/accounts/auth/login/",
        "/api/v1/accounts/auth/logout/",
        "/api/v1/accounts/me/",
        "/api/v1/public/core/health/",
    ):
        assert path in paths


@pytest.mark.django_db
def test_swagger_ui_is_served(public_api):
    assert public_api.get("/api/docs/").status_code == 200


def _schema():
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.mark.urls("apps.core.tests.tenancy_urls")
def test_property_scoped_views_document_the_property_header():
    paths = _schema()["paths"]
    for path, method in (
        ("/t/ping/", "get"),
        ("/t/ping/", "post"),
        ("/t/alerts/", "get"),
        ("/t/roles/", "get"),
    ):
        headers = [p for p in paths[path][method].get("parameters", []) if p["in"] == "header"]
        assert {"name": "X-Property-Id", "in": "header", "required": True} in [
            {key: h[key] for key in ("name", "in", "required")} for h in headers
        ], f"{method} {path}"


def test_the_schema_generates_without_warnings(tmp_path):
    """The CI command `manage.py spectacular --validate --fail-on-warn` must pass with every app's API: the
    `kind`/`status`/`source` choices that differ between apps would otherwise get hashed names such as
    `KindD0cEnum` (unstable for generated clients) and a warning each."""
    from django.core.management import call_command

    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yaml"))


def test_colliding_enums_get_stable_names():
    schemas = _schema()["components"]["schemas"]
    for name in (
        "BookingStatusEnum",
        "ReservationSourceEnum",
        "RoomTypeKindEnum",
        "RoomBlockKindEnum",
        "GuestDocumentKindEnum",
    ):
        assert name in schemas, name


def test_session_cookie_auth_is_documented_and_auth_views_are_typed():
    schema = _schema()
    assert "cookieAuth" in schema["components"]["securitySchemes"]
    login = schema["paths"]["/api/v1/accounts/auth/login/"]["post"]
    assert "requestBody" in login and "200" in login["responses"]
    me = schema["paths"]["/api/v1/accounts/me/"]
    assert me["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/Me")
    assert "204" in schema["paths"]["/api/v1/accounts/auth/logout/"]["post"]["responses"]
