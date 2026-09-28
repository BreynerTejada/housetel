"""Template editor API: effective templates (property → organization → system), CRUD of overrides, preview and
the variables catalog."""

from datetime import date

import pytest

from apps.bookings.tests.factories import ReservationFactory
from apps.core.models import AuditEvent
from apps.core.tests.factories import PropertyFactory
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import MessageTemplate
from apps.messaging.tests.factories import ConversationFactory, MessageTemplateFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/messaging/templates/"


def _find(rows, code, channel="email", language="es"):
    return next(r for r in rows if (r["code"], r["channel"], r["language"]) == (code, channel, language))


class TestEffectiveList:
    def test_every_system_template_is_listed_with_its_source(self, api):
        rows = api.get(URL).json()
        codes = {row["code"] for row in rows}
        assert codes == {
            "confirmation",
            "pre_arrival",
            "arrival_day",
            "post_stay",
            "payment_reminder",
            "cancellation",
            "checkin_invitation",
            "payment_link",
        }
        assert len(rows) == 8 * 2 * 2
        row = _find(rows, "payment_link", "whatsapp", "en")
        assert (row["source"], row["id"], row["is_system_code"], row["subject"]) == ("system", None, True, "")
        assert row["label"] == {"es": "Link de pago", "en": "Payment link"}
        assert "{{payment_url}}" in row["body"]
        assert (row["organization_template_id"], row["property_template_id"]) == (None, None)

    def test_overrides_replace_the_system_text(self, api, prop):
        org_row = MessageTemplateFactory(
            property=None, organization=prop.organization, body="Org {{guest.first_name}}"
        )
        prop_row = MessageTemplateFactory(
            property=prop, code="confirmation", channel="whatsapp", subject="", body="Hotel"
        )
        rows = api.get(URL).json()
        email = _find(rows, "confirmation")
        assert (email["source"], email["id"], email["body"]) == (
            "organization",
            str(org_row.pk),
            org_row.body,
        )
        assert email["organization_template_id"] == str(org_row.pk)
        whatsapp = _find(rows, "confirmation", "whatsapp")
        assert (whatsapp["source"], whatsapp["id"], whatsapp["property_template_id"]) == (
            "property",
            str(prop_row.pk),
            str(prop_row.pk),
        )

    def test_custom_codes_are_listed(self, api, prop):
        MessageTemplateFactory(property=prop, code="welcome_drink", name="Cóctel de bienvenida", body="Salud")
        row = _find(api.get(URL).json(), "welcome_drink")
        assert (row["is_system_code"], row["label"], row["source"]) == (
            False,
            {"es": "Cóctel de bienvenida", "en": "Cóctel de bienvenida"},
            "property",
        )

    def test_sibling_hotels_and_other_organizations_never_leak(self, api, prop):
        MessageTemplateFactory(property=PropertyFactory(organization=prop.organization), body="Hermano")
        MessageTemplateFactory(property=None, organization=PropertyFactory().organization, body="Otra org")
        assert _find(api.get(URL).json(), "confirmation")["source"] == "system"


class TestWrite:
    def test_customize_for_this_hotel(self, api, prop, owner):
        response = api.post(
            URL,
            {
                "code": "confirmation",
                "channel": "email",
                "language": "es",
                "scope": "property",
                "subject": "¡Listo, {{guest.first_name}}!",
                "body": "Te esperamos el {{reservation.checkin}}.",
            },
            format="json",
        )

        assert response.status_code == 201
        data = response.json()
        row = MessageTemplate.objects.get(pk=data["id"])
        assert (row.property, row.organization, row.updated_by, data["scope"]) == (
            prop,
            prop.organization,
            owner,
            "property",
        )
        assert _find(api.get(URL).json(), "confirmation")["source"] == "property"

    def test_customize_for_the_whole_organization(self, api, prop):
        response = api.post(
            URL,
            {
                "code": "arrival_day",
                "channel": "whatsapp",
                "language": "en",
                "scope": "organization",
                "body": "Welcome!",
            },
            format="json",
        )
        assert response.status_code == 201
        row = MessageTemplate.objects.get(pk=response.json()["id"])
        assert (row.property, row.organization) == (None, prop.organization)

    def test_a_member_limited_to_some_hotels_cannot_change_the_organization(self, api_for, prop, make_member):
        manager = make_member("manager", properties=[prop])
        response = api_for(manager, prop).post(
            URL,
            {
                "code": "arrival_day",
                "channel": "whatsapp",
                "language": "es",
                "scope": "organization",
                "body": "Hola",
            },
            format="json",
        )
        assert response.status_code == 403 and response.json()["code"] == "organization_scope_forbidden"
        response = api_for(manager, prop).post(
            URL,
            {
                "code": "arrival_day",
                "channel": "whatsapp",
                "language": "es",
                "scope": "property",
                "body": "Hola",
            },
            format="json",
        )
        assert response.status_code == 201

    def test_one_override_per_scope(self, api, prop):
        existing = MessageTemplateFactory(property=prop)
        response = api.post(
            URL,
            {
                "code": "confirmation",
                "channel": "email",
                "language": "es",
                "scope": "property",
                "subject": "x",
                "body": "y",
            },
            format="json",
        )
        assert response.status_code == 409
        assert (response.json()["code"], response.json()["id"]) == ("template_exists", str(existing.pk))

    def test_validation(self, api):
        def post(**body):
            values = {
                "code": "confirmation",
                "channel": "email",
                "language": "es",
                "scope": "property",
                "subject": "Hola",
                "body": "Hola",
            }
            values.update(body)
            return api.post(URL, values, format="json")

        response = post(subject="")
        assert response.status_code == 400 and "subject" in response.json()["fields"]
        response = post(body="Hola {{guest.apodo}} {{reservation.codigo}}")
        assert response.status_code == 400
        assert response.json()["fields"]["body"] == [
            "Variables desconocidas: guest.apodo, reservation.codigo"
        ]
        response = post(code="Mi Plantilla!")
        assert response.status_code == 400 and "code" in response.json()["fields"]
        response = post(code="welcome_drink", name="")
        assert response.status_code == 400 and "name" in response.json()["fields"]
        response = post(code="custom_message", name="Libre")  # reserved for free text sent by other modules
        assert response.status_code == 400 and "code" in response.json()["fields"]
        response = post(
            channel="whatsapp",
            subject="",
            wa_template_name="bienvenida",
            wa_template_params=["guest.first_name", "nope"],
        )
        assert response.status_code == 400 and "wa_template_params" in response.json()["fields"]

    def test_edit_and_restore_the_inherited_text(self, api, prop):
        row = MessageTemplateFactory(property=prop, body="Viejo")
        response = api.patch(
            f"{URL}{row.pk}/", {"body": "Nuevo {{guest.first_name}}", "is_active": False}, format="json"
        )
        assert response.status_code == 200
        row.refresh_from_db()
        assert (row.body, row.is_active) == ("Nuevo {{guest.first_name}}", False)

        assert api.delete(f"{URL}{row.pk}/").status_code == 204
        assert _find(api.get(URL).json(), "confirmation")["source"] == "system"

    def test_the_code_channel_language_and_scope_are_fixed(self, api, prop):
        row = MessageTemplateFactory(property=prop)
        api.patch(
            f"{URL}{row.pk}/", {"code": "other", "channel": "whatsapp", "language": "en"}, format="json"
        )
        row.refresh_from_db()
        assert (row.code, row.channel, row.language) == ("confirmation", "email", "es")

    def test_rows_of_other_hotels_cannot_be_touched(self, api, prop):
        sibling_row = MessageTemplateFactory(property=PropertyFactory(organization=prop.organization))
        stranger_row = MessageTemplateFactory(property=None, organization=PropertyFactory().organization)
        for row in (sibling_row, stranger_row):
            assert api.patch(f"{URL}{row.pk}/", {"body": "x"}, format="json").status_code == 404
            assert api.delete(f"{URL}{row.pk}/").status_code == 404

    def test_organization_rows_need_all_hotels_to_be_edited(self, api_for, prop, make_member):
        org_row = MessageTemplateFactory(property=None, organization=prop.organization)
        limited = api_for(make_member("manager", properties=[prop]), prop)
        response = limited.patch(f"{URL}{org_row.pk}/", {"body": "x"}, format="json")
        assert response.status_code == 403 and response.json()["code"] == "organization_scope_forbidden"

    def test_every_change_is_audited(self, api, prop, owner):
        created = api.post(
            URL,
            {
                "code": "confirmation",
                "channel": "email",
                "language": "es",
                "scope": "property",
                "subject": "Hola",
                "body": "Viejo",
            },
            format="json",
        ).json()
        api.patch(f"{URL}{created['id']}/", {"body": "Nuevo"}, format="json")
        api.delete(f"{URL}{created['id']}/")

        events = AuditEvent.objects.filter(target_id=created["id"]).order_by("created_at")
        assert [(e.action, e.actor, e.property, e.target_type) for e in events] == [
            ("messaging.template_created", owner, prop, "messaging.messagetemplate"),
            ("messaging.template_updated", owner, prop, "messaging.messagetemplate"),
            ("messaging.template_deleted", owner, prop, "messaging.messagetemplate"),
        ]
        assert events[1].changes == {"body": ["Viejo", "Nuevo"]}

    def test_an_organization_template_is_audited_for_the_organization(self, api, prop):
        created = api.post(
            URL,
            {
                "code": "arrival_day",
                "channel": "whatsapp",
                "language": "es",
                "scope": "organization",
                "body": "Hola",
            },
            format="json",
        ).json()
        event = AuditEvent.objects.get(target_id=created["id"])
        assert (event.property, event.organization) == (None, prop.organization)


class TestPermissions:
    def test_front_desk_reads_templates_but_cannot_edit_them(self, api_for, prop, make_member):
        client = api_for(make_member("front_desk"), prop)
        assert client.get(URL).status_code == 200
        response = client.post(
            URL,
            {
                "code": "confirmation",
                "channel": "email",
                "language": "es",
                "scope": "property",
                "subject": "x",
                "body": "y",
            },
            format="json",
        )
        assert response.status_code == 403 and response.json()["permission"] == "messaging.templates"

    def test_housekeeping_sees_nothing(self, api_for, prop, make_member):
        assert api_for(make_member("housekeeping"), prop).get(URL).status_code == 403


class TestPreview:
    def test_a_draft_with_sample_values(self, api, prop):
        response = api.post(
            f"{URL}preview/",
            {
                "channel": "email",
                "language": "es",
                "subject": "Hola {{guest.first_name}}",
                "body": "**Código:** {{reservation.code}}\n\n[Ver]({{portal_url}})\n\n{{guest.apodo}}",
            },
            format="json",
        )

        assert response.status_code == 200
        data = response.json()
        assert (data["subject"], data["sample"], data["source"]) == ("Hola Ana", True, "draft")
        assert data["text"].startswith("Código: HT-7K2M9Q\n\nVer: https://")
        assert data["markup"].startswith("**Código:** HT-7K2M9Q\n\n[Ver](https://")
        assert data["unknown"] == ["guest.apodo"]
        assert prop.name in data["html"] and "<strong>Código:</strong>" in data["html"]

    def test_the_effective_template_for_a_real_reservation(self, api, prop):
        guest = GuestFactory(organization=prop.organization, first_name="Mateo", language="en")
        reservation = ReservationFactory(
            property=prop,
            booker=guest,
            code="HT-MATEO1",
            checkin_date=date(2026, 10, 9),
            checkout_date=date(2026, 10, 11),
        )
        response = api.post(
            f"{URL}preview/",
            {"template_code": "confirmation", "channel": "whatsapp", "reservation_id": str(reservation.pk)},
            format="json",
        )
        data = response.json()
        assert (data["language"], data["source"], data["sample"]) == ("en", "system", False)
        assert "Hi Mateo!" in data["whatsapp"] and "*Code:* HT-MATEO1" in data["whatsapp"]
        assert data["missing"] == [] and data["html"] == ""

    def test_the_context_of_a_conversation(self, api, prop):
        guest = GuestFactory(organization=prop.organization, first_name="Sofía")
        conversation = ConversationFactory(property=prop, guest=guest, channel="whatsapp")
        data = api.post(
            f"{URL}preview/",
            {"template_code": "post_stay", "channel": "whatsapp", "conversation_id": str(conversation.pk)},
            format="json",
        ).json()
        assert "Sofía" in data["whatsapp"] and data["sample"] is False

    def test_missing_values_are_reported(self, api, prop):
        guest = GuestFactory(organization=prop.organization, first_name="Sofía")
        conversation = ConversationFactory(property=prop, guest=guest)
        data = api.post(
            f"{URL}preview/",
            {"template_code": "confirmation", "channel": "whatsapp", "conversation_id": str(conversation.pk)},
            format="json",
        ).json()
        assert "reservation.code" in data["missing"]

    def test_unknown_codes_and_foreign_objects(self, api):
        response = api.post(f"{URL}preview/", {"template_code": "nope", "channel": "email"}, format="json")
        assert response.status_code == 400 and response.json()["code"] == "template_not_found"
        foreign = ReservationFactory(property=PropertyFactory())
        response = api.post(
            f"{URL}preview/",
            {"template_code": "confirmation", "channel": "email", "reservation_id": str(foreign.pk)},
            format="json",
        )
        assert response.status_code == 404


def test_the_variables_catalog(api):
    rows = api.get("/api/v1/messaging/variables/").json()
    first = rows[0]
    assert first == {
        "key": "guest.first_name",
        "group": "guest",
        "label": {"es": "Nombre del huésped", "en": "Guest first name"},
        "example": {"es": "Ana", "en": "Ana"},
    }
    keys = {row["key"] for row in rows}
    assert {"reservation.code", "portal_url", "checkin_url", "payment_url", "balance", "nights"} <= keys
