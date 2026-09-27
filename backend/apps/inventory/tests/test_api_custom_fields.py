"""`/api/v1/inventory/custom-fields/`: hotel-defined fields for room types, rooms, guests and reservations."""

import pytest

from apps.core.tests.factories import PropertyFactory
from apps.inventory.models import CustomFieldDefinition, Room, RoomType
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db
URL = f"{BASE}/custom-fields/"


def define(organization, key, applies_to="room", property=None, **extra):
    extra.setdefault("field_type", "text")
    return CustomFieldDefinition.objects.create(
        organization=organization, property=property, applies_to=applies_to, key=key,
        label={"es": key.title()}, **extra,
    )  # fmt: skip


class TestList:
    def test_organization_and_own_property_definitions(self, api, prop, organization):
        define(organization, "minibar", field_type="boolean")
        define(organization, "orientation", applies_to="room_type", property=prop)
        define(organization, "secret", property=PropertyFactory(organization=organization))
        define(PropertyFactory().organization, "foreign")
        rows = api.get(URL).json()
        assert {(row["key"], row["scope"]) for row in rows} == {
            ("minibar", "organization"),
            ("orientation", "property"),
        }

    def test_filters_by_what_they_apply_to(self, api, organization):
        define(organization, "minibar")
        define(organization, "vip_code", applies_to="guest")
        assert [row["key"] for row in api.get(f"{URL}?applies_to=guest").json()] == ["vip_code"]


class TestCreate:
    def test_creates_a_select_field_normalizing_options(self, api, prop, organization):
        response = api.post(
            URL,
            {
                "applies_to": "room_type",
                "key": "orientation",
                "label": {"es": "Orientación", "en": "Orientation"},
                "field_type": "select",
                "options": ["mar", {"value": "ciudad", "label": {"es": "Ciudad", "en": "City"}}],
                "default_value": "ciudad",
                "show_in_marketplace": True,
            },
        )
        assert response.status_code == 201, response.json()
        definition = CustomFieldDefinition.objects.get(pk=response.json()["id"])
        assert (definition.organization, definition.property, definition.default_value) == (
            organization,
            None,
            "ciudad",
        )
        assert definition.options == [
            {"value": "mar", "label": {"es": "mar"}},
            {"value": "ciudad", "label": {"es": "Ciudad", "en": "City"}},
        ]

    def test_property_scope(self, api, prop):
        response = api.post(
            URL, {"applies_to": "room", "key": "safe_code", "label": "Caja fuerte", "scope": "property"}
        )
        assert response.status_code == 201
        assert CustomFieldDefinition.objects.get(pk=response.json()["id"]).property == prop

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"key": "Mini Bar"}, "key"),
            ({"key": "minibar", "field_type": "select", "options": []}, "options"),
            ({"key": "minibar", "field_type": "select", "options": ["a", "a"]}, "options"),
            ({"key": "minibar", "field_type": "boolean", "default_value": "yes"}, "default_value"),
            (
                {"key": "minibar", "field_type": "select", "options": ["a"], "default_value": "b"},
                "default_value",
            ),
            ({"key": "minibar", "label": {"es": ""}}, "label"),
            ({"key": "minibar", "applies_to": "invoice"}, "applies_to"),
        ],
    )
    def test_validation(self, api, payload, field):
        body = {"applies_to": "room", "label": {"es": "Minibar"}, "field_type": "text", **payload}
        response = api.post(URL, body)
        assert response.status_code == 400 and field in response.json()["fields"], response.json()

    def test_creation_is_audited_together_with_the_definition(self, api, owner, monkeypatch):
        from apps.core import audit
        from apps.core.models import AuditEvent

        body = {"applies_to": "room", "key": "safe_code", "label": "Caja fuerte"}
        definition_id = api.post(URL, body).json()["id"]
        event = AuditEvent.objects.get(action="inventory.custom_field_created")
        assert (event.target_id, event.actor) == (definition_id, owner)

        def broken_audit(**kwargs):
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit, "record", broken_audit)
        with pytest.raises(RuntimeError):
            api.post(URL, {**body, "key": "safe_code_2"})
        assert not CustomFieldDefinition.objects.filter(key="safe_code_2").exists()  # never unaudited

    def test_keys_are_unique_across_scopes(self, api, prop, organization):
        define(organization, "minibar", property=prop)
        response = api.post(URL, {"applies_to": "room", "key": "minibar", "label": "Minibar"})
        assert response.status_code == 400 and "key" in response.json()["fields"]

    @pytest.mark.parametrize(("existing", "new"), [("room_type", "room"), ("room", "room_type")])
    def test_room_and_category_fields_share_one_namespace(self, api, organization, existing, new):
        """A room inherits its category's values and overrides them by key, so a room field and a category
        field with the same key would be ambiguous."""
        define(organization, "orientation", applies_to=existing)
        response = api.post(URL, {"applies_to": new, "key": "orientation", "label": "Orientación"})
        assert response.status_code == 400 and "key" in response.json()["fields"]

    def test_guest_and_reservation_keys_do_not_clash_with_inventory_keys(self, api, organization):
        define(organization, "notes_extra", applies_to="room")
        response = api.post(URL, {"applies_to": "guest", "key": "notes_extra", "label": "Notas"})
        assert response.status_code == 201, response.json()


class TestUpdateAndDelete:
    def test_key_type_and_target_cannot_change(self, api, organization):
        definition = define(organization, "minibar", field_type="boolean")
        response = api.patch(
            f"{URL}{definition.pk}/", {"key": "bar", "field_type": "text", "applies_to": "guest"}
        )
        assert response.status_code == 400
        assert {"key", "field_type", "applies_to"} <= set(response.json()["fields"])

    def test_label_options_and_flags_can_change(self, api, organization):
        definition = define(organization, "orientation", field_type="select", options=[{"value": "sea"}])
        response = api.patch(
            f"{URL}{definition.pk}/", {"label": {"es": "Vista"}, "options": ["sea", "city"], "required": True}
        )
        assert response.status_code == 200, response.json()
        definition.refresh_from_db()
        assert (definition.label, definition.required, len(definition.options)) == ({"es": "Vista"}, True, 2)

    def test_removing_options_clears_the_values_that_used_them(self, api, prop, organization):
        definition = define(
            organization, "orientation", applies_to="room_type", field_type="select",
            options=[{"value": "sea"}, {"value": "city"}, {"value": "garden"}],
        )  # fmt: skip
        views = define(
            organization, "views", applies_to="room", field_type="multiselect",
            options=[{"value": "sea"}, {"value": "garden"}],
        )  # fmt: skip
        garden_type = RoomTypeFactory(property=prop, custom_values={"orientation": "garden"})
        sea_type = RoomTypeFactory(property=prop, custom_values={"orientation": "sea"})
        overriding = RoomFactory(
            room_type=sea_type, custom_values={"orientation": "garden", "views": ["sea", "garden"]}
        )
        keeping = RoomFactory(room_type=garden_type, custom_values={"orientation": "city"})

        assert api.patch(f"{URL}{definition.pk}/", {"options": ["sea", "city"]}).status_code == 200
        assert api.patch(f"{URL}{views.pk}/", {"options": ["sea"]}).status_code == 200

        assert RoomType.objects.get(pk=garden_type.pk).custom_values == {}
        assert RoomType.objects.get(pk=sea_type.pk).custom_values == {"orientation": "sea"}
        assert Room.objects.get(pk=overriding.pk).custom_values == {"views": ["sea"]}
        assert Room.objects.get(pk=keeping.pk).custom_values == {"orientation": "city"}

    def test_a_room_still_saves_after_an_option_it_used_was_removed(self, api, prop, organization):
        definition = define(
            organization, "orientation", applies_to="room_type", field_type="select",
            options=[{"value": "sea"}, {"value": "garden"}],
        )  # fmt: skip
        room = RoomFactory(room_type__property=prop, custom_values={"orientation": "garden"})
        api.patch(f"{URL}{definition.pk}/", {"options": ["sea"]})

        response = api.patch(
            f"{BASE}/rooms/{room.pk}/",
            {"floor": "4", "custom_values": Room.objects.get(pk=room.pk).custom_values},
        )
        assert response.status_code == 200, response.json()

    def test_deleting_removes_the_values_from_rooms_and_categories(self, api, prop, organization):
        room_field = define(organization, "minibar", field_type="boolean")
        type_field = define(organization, "orientation", applies_to="room_type")
        room_type = RoomTypeFactory(property=prop, custom_values={"orientation": "sea", "keep": 1})
        room = RoomFactory(room_type=room_type, custom_values={"minibar": True, "orientation": "city"})

        assert api.delete(f"{URL}{room_field.pk}/").status_code == 204
        assert api.delete(f"{URL}{type_field.pk}/").status_code == 204

        assert Room.objects.get(pk=room.pk).custom_values == {}
        assert RoomType.objects.get(pk=room_type.pk).custom_values == {"keep": 1}
        assert not CustomFieldDefinition.objects.exists()

    def test_definitions_of_another_property_are_not_reachable(self, api, organization):
        hidden = define(organization, "secret", property=PropertyFactory(organization=organization))
        assert api.delete(f"{URL}{hidden.pk}/").status_code == 404
