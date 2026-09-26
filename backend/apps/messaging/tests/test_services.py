"""Phase A stub (plan Step 5): send_message only logs and returns []; C6 implements real delivery."""

import logging

import pytest

from apps.messaging.services import send_message

pytestmark = pytest.mark.django_db


def test_stub_logs_and_returns_no_messages(prop, caplog):
    with caplog.at_level(logging.INFO, logger="housetel.messaging"):
        result = send_message(
            property=prop,
            template_code="confirmation",
            to="guest@example.com",
            channels=("email", "whatsapp"),
            context={"code": "HT-ABC123"},
        )
    assert result == []
    assert "confirmation" in caplog.text and str(prop.pk) in caplog.text
