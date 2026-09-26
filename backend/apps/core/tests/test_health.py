def test_health_is_public_and_needs_no_database(public_api):
    # No `db` fixture: the endpoint must answer without touching the database or a session.
    response = public_api.get("/api/v1/public/core/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_writes(public_api):
    response = public_api.post("/api/v1/public/core/health/", {})
    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
