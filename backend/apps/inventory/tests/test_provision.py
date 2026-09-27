"""`provision_room_type` (plan §C): one call creates a category with its rooms, dorm beds and amenities.

Used by AI onboarding (C9) and signup (C11), so it validates everything, normalizes the obviously safe
conversions and creates nothing when any part is invalid.
"""

from decimal import Decimal

import pytest

from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.signals import inventory_changed
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.inventory.models import Bed, CustomFieldDefinition, Room, RoomType
from apps.inventory.services import provision_room_type
from apps.inventory.tests.factories import AmenityFactory, RoomFactory, RoomTypeFactory
from apps.inventory.tests.test_services_basic import listen

pytestmark = pytest.mark.django_db


def suite_data(**overrides):
    data = {
        "code": "STE",
        "name": {"es": "Suite Vista al Mar", "en": "Sea View Suite"},
        "kind": "private",
        "base_occupancy": 2,
        "max_adults": 3,
        "max_children": 1,
        "max_occupancy": 4,
        "beds": [{"type": "king", "count": 1}],
        "size_m2": "42.50",
        "view": "sea",
        "amenities": ["wifi", "bathtub"],
        "color": "#B4583B",
        "housekeeping_minutes": 45,
    }
    data.update(overrides)
    return data


@pytest.fixture
def catalog():
    return {code: AmenityFactory(code=code) for code in ("wifi", "bathtub", "tv")}


def assert_nothing_created():
    assert not RoomType.objects.exists() and not Room.objects.exists() and not Bed.objects.exists()


class TestCreates:
    def test_the_category_its_rooms_and_amenities(self, prop, owner, catalog):
        room_type = provision_room_type(
            prop, data=suite_data(), room_numbers=["301", "302", "303"], floor="3", actor=owner
        )

        room_type.refresh_from_db()
        assert room_type.property == prop
        assert (room_type.code, room_type.name, room_type.kind) == (
            "STE",
            {"es": "Suite Vista al Mar", "en": "Sea View Suite"},
            "private",
        )
        assert (
            room_type.base_occupancy,
            room_type.max_adults,
            room_type.max_children,
            room_type.max_occupancy,
        ) == (2, 3, 1, 4)
        assert room_type.beds == [{"type": "king", "count": 1}]
        assert (room_type.size_m2, room_type.view, room_type.color, room_type.housekeeping_minutes) == (
            Decimal("42.50"),
            "sea",
            "#B4583B",
            45,
        )
        assert sorted(room_type.amenities.values_list("code", flat=True)) == ["bathtub", "wifi"]
        rooms = Room.objects.filter(room_type=room_type).order_by("number")
        assert [(r.number, r.floor, r.property_id, r.is_active) for r in rooms] == [
            ("301", "3", prop.pk, True),
            ("302", "3", prop.pk, True),
            ("303", "3", prop.pk, True),
        ]

    def test_infers_each_room_floor_when_floor_is_not_given(self, prop):
        room_type = provision_room_type(
            prop, data=suite_data(amenities=[]), room_numbers=["101", "205", "D1"]
        )
        floors = dict(Room.objects.filter(room_type=room_type).values_list("number", "floor"))
        assert floors == {"101": "1", "205": "2", "D1": ""}

    def test_an_empty_floor_is_kept_empty(self, prop):
        room_type = provision_room_type(prop, data=suite_data(amenities=[]), room_numbers=["101"], floor="")
        assert room_type.rooms.get().floor == ""

    def test_room_numbers_may_contain_ranges(self, prop):
        room_type = provision_room_type(prop, data=suite_data(amenities=[]), room_numbers=["101-103", "110"])
        assert sorted(room_type.rooms.values_list("number", flat=True)) == ["101", "102", "103", "110"]

    def test_a_category_without_rooms_is_allowed(self, prop):
        room_type = provision_room_type(prop, data=suite_data(amenities=[]), room_numbers=[])
        assert room_type.pk and not room_type.rooms.exists()

    def test_resolves_organization_amenities_but_not_other_organizations(self, prop, catalog):
        AmenityFactory(code="hammock", organization=prop.organization)
        room_type = provision_room_type(prop, data=suite_data(amenities=["hammock", "wifi"]), room_numbers=[])
        assert sorted(room_type.amenities.values_list("code", flat=True)) == ["hammock", "wifi"]

        AmenityFactory(code="jacuzzi", organization=OrganizationFactory())
        with pytest.raises(DomainError) as exc:
            provision_room_type(prop, data=suite_data(code="SUP", amenities=["jacuzzi"]), room_numbers=[])
        assert exc.value.code == "validation_error"
        assert "jacuzzi" in str(exc.value.extra["fields"]["amenities"])

    def test_new_categories_are_sorted_after_the_existing_ones(self, prop):
        RoomTypeFactory(property=prop, sort_order=40)
        room_type = provision_room_type(prop, data=suite_data(amenities=[]), room_numbers=[])
        assert room_type.sort_order > 40

    def test_works_inside_the_callers_transaction(self, prop):
        from django.db import transaction

        with transaction.atomic():
            first = provision_room_type(prop, data=suite_data(amenities=[]), room_numbers=["101"])
            second = provision_room_type(
                prop, data=suite_data(code="SUP", amenities=[]), room_numbers=["201"]
            )
        assert {first.code, second.code} == {"STE", "SUP"}


class TestDorms:
    def test_creates_the_beds_of_every_dorm_room(self, prop):
        room_type = provision_room_type(
            prop,
            data={"code": "D6", "name": {"es": "Dormitorio mixto 6 camas"}, "kind": "dorm"},
            room_numbers=["D1", "D2"],
            beds_per_room=6,
        )
        for room in room_type.rooms.all():
            assert list(room.beds.order_by("created_at").values_list("label", flat=True)) == [
                "C1",
                "C2",
                "C3",
                "C4",
                "C5",
                "C6",
            ]
        assert Bed.objects.filter(room__room_type=room_type, is_active=True).count() == 12

    def test_dorm_units_are_beds_for_one_person(self, prop):
        room_type = provision_room_type(
            prop,
            data={"code": "D8", "name": "Dorm 8", "kind": "dorm", "max_occupancy": 8, "max_adults": 8},
            room_numbers=[],
        )
        assert (
            room_type.base_occupancy,
            room_type.max_adults,
            room_type.max_children,
            room_type.max_occupancy,
        ) == (1, 1, 0, 1)

    def test_bunk_beds_count_twice_when_beds_per_room_is_not_given(self, prop):
        room_type = provision_room_type(
            prop,
            data={"code": "D4", "name": "Dorm 4", "kind": "dorm", "beds": [{"type": "bunk", "count": 2}]},
            room_numbers=["D1"],
        )
        beds = list(room_type.rooms.get().beds.order_by("created_at").values_list("label", "bed_type"))
        assert beds == [("C1", "bunk_bottom"), ("C2", "bunk_top"), ("C3", "bunk_bottom"), ("C4", "bunk_top")]

    def test_beds_per_room_is_ignored_for_private_categories(self, prop):
        room_type = provision_room_type(
            prop, data=suite_data(amenities=[]), room_numbers=["101"], beds_per_room=2
        )
        assert not Bed.objects.filter(room__room_type=room_type).exists()


class TestNormalizes:
    def test_a_plain_name_and_a_lowercase_code(self, prop):
        room_type = provision_room_type(
            prop, data={"code": " dbl ", "name": "Doble estándar"}, room_numbers=[]
        )
        assert (room_type.code, room_type.name) == ("DBL", {"es": "Doble estándar"})

    def test_a_missing_code_is_derived_from_the_name_and_kept_unique(self, prop):
        RoomTypeFactory(property=prop, code="SVM")
        room_type = provision_room_type(prop, data={"name": {"es": "Suite Vista al Mar"}}, room_numbers=[])
        assert room_type.code == "SVM2"
        single_word = provision_room_type(prop, data={"name": {"es": "Estándar"}}, room_numbers=[])
        assert single_word.code == "EST"

    def test_unknown_keys_are_ignored_so_proposals_can_be_passed_as_they_are(self, prop):
        room_type = provision_room_type(
            prop,
            data=suite_data(amenities=[], units=3, base_price="320000", room_numbers=["1"], floor="9"),
            room_numbers=["101"],
        )
        assert room_type.rooms.get().number == "101"

    @pytest.mark.parametrize(
        ("given", "code"),
        [
            ("Suite Vista", "SUITE-VISTA"),
            ("suíte", "SUITE"),
            ("  Dbl/Queen  ", "DBL-QUEEN"),
            ("SUITE_VISTA_AL_MAR_PREMIUM", "SUITE_VISTA_AL_MAR_P"),
            ("--doble--", "DOBLE"),
            ("ÑÑ ÑÑ", "NN-NN"),
            (305, "305"),
        ],
    )
    def test_a_generated_code_is_turned_into_a_valid_one(self, prop, given, code):
        room_type = provision_room_type(prop, data=suite_data(code=given, amenities=[]), room_numbers=[])
        assert room_type.code == code

    def test_a_code_with_nothing_usable_is_derived_from_the_name(self, prop):
        room_type = provision_room_type(prop, data=suite_data(code="¿?", amenities=[]), room_numbers=[])
        assert room_type.code == "SVM"

    def test_case_of_kind_and_bed_types_and_extra_decimals(self, prop):
        room_type = provision_room_type(
            prop,
            data={
                "name": "Dormitorio",
                "kind": " Dorm ",
                "beds": [{"type": "Bunk", "count": 2}],
                "size_m2": 24.335,
            },
            room_numbers=["D1"],
        )
        assert (room_type.kind, room_type.beds, room_type.size_m2) == (
            "dorm",
            [{"type": "bunk", "count": 2}],
            Decimal("24.34"),
        )
        assert room_type.rooms.get().beds.count() == 4


class TestValidates:
    @pytest.mark.parametrize(
        ("overrides", "field"),
        [
            ({"kind": "suite"}, "kind"),
            ({"name": {"es": "", "en": ""}}, "name"),
            ({"name": None}, "name"),
            ({"max_adults": 5, "max_occupancy": 4}, "max_adults"),
            ({"base_occupancy": 5, "max_occupancy": 4}, "base_occupancy"),
            ({"max_children": 4, "max_occupancy": 4}, "max_children"),
            ({"max_occupancy": 0}, "max_occupancy"),
            ({"beds": [{"type": "hammock", "count": 1}]}, "beds"),
            ({"beds": [{"type": "king", "count": 0}]}, "beds"),
            ({"beds": "king"}, "beds"),
            ({"size_m2": "-3"}, "size_m2"),
            ({"color": "terracota"}, "color"),
            ({"housekeeping_minutes": 0}, "housekeeping_minutes"),
            ({"amenities": ["wifi", "moon-pool"]}, "amenities"),
        ],
    )
    def test_reports_the_invalid_field_and_creates_nothing(self, prop, catalog, overrides, field):
        with pytest.raises(DomainError) as exc:
            provision_room_type(prop, data=suite_data(**overrides), room_numbers=["301"])
        assert exc.value.code == "validation_error" and exc.value.status_code == 400
        assert field in exc.value.extra["fields"]
        assert_nothing_created()

    def test_rejects_a_code_already_used_in_the_property(self, prop, catalog):
        RoomTypeFactory(property=prop, code="STE")
        RoomTypeFactory(property=PropertyFactory(organization=prop.organization), code="SUP")
        with pytest.raises(DomainError) as exc:
            provision_room_type(prop, data=suite_data(), room_numbers=[])
        assert "code" in exc.value.extra["fields"]
        assert provision_room_type(prop, data=suite_data(code="SUP"), room_numbers=[]).code == "SUP"

    def test_rejects_data_that_is_not_an_object(self, prop):
        with pytest.raises(DomainError) as exc:
            provision_room_type(prop, data=["STE"], room_numbers=[])
        assert exc.value.code == "validation_error"

    def test_rejects_room_numbers_that_exist_or_repeat(self, prop, catalog):
        RoomFactory(room_type__property=prop, number="301")
        rooms_before = Room.objects.count()
        with pytest.raises(DomainError) as exc:
            provision_room_type(prop, data=suite_data(), room_numbers=["301", "302", "302"])
        assert exc.value.code == "duplicate_room_numbers"
        assert exc.value.extra["duplicates"] == ["301", "302"]
        assert "room_numbers" in exc.value.extra["fields"]
        assert (RoomType.objects.filter(code="STE").exists(), Room.objects.count()) == (False, rooms_before)

    def test_rejects_invalid_ranges(self, prop, catalog):
        with pytest.raises(DomainError) as exc:
            provision_room_type(prop, data=suite_data(), room_numbers=["310-301"])
        assert exc.value.code == "invalid_room_numbers"
        assert_nothing_created()

    @pytest.mark.parametrize("extra", [{"beds_per_room": 0}, {}], ids=["zero", "no-bed-configuration"])
    def test_dorm_rooms_need_at_least_one_bed(self, prop, extra):
        with pytest.raises(DomainError) as exc:
            provision_room_type(
                prop, data={"code": "D6", "name": "Dorm", "kind": "dorm", "beds": []}, room_numbers=["D1"],
                **extra,
            )  # fmt: skip
        assert exc.value.code == "validation_error" and "beds_per_room" in exc.value.extra["fields"]
        assert_nothing_created()

    def test_a_dorm_category_without_rooms_needs_no_beds(self, prop):
        room_type = provision_room_type(
            prop, data={"code": "D6", "name": "Dorm", "kind": "dorm"}, room_numbers=[]
        )
        assert (room_type.kind, room_type.rooms.count()) == ("dorm", 0)

    @pytest.mark.parametrize("beds_per_room", [-1, 51])
    def test_rejects_an_out_of_range_beds_per_room_for_dorms(self, prop, beds_per_room):
        with pytest.raises(DomainError) as exc:
            provision_room_type(
                prop, data={"code": "D6", "name": "Dorm", "kind": "dorm"}, room_numbers=["D1"],
                beds_per_room=beds_per_room,
            )  # fmt: skip
        assert exc.value.code == "validation_error" and "beds_per_room" in exc.value.extra["fields"]
        assert_nothing_created()

    def test_validates_custom_values_against_the_room_type_definitions(self, prop, catalog):
        CustomFieldDefinition.objects.create(
            organization=prop.organization,
            applies_to="room_type",
            key="orientation",
            field_type="select",
            label={"es": "Orientación"},
            options=[{"value": "sea"}, {"value": "city"}],
        )
        ok = provision_room_type(prop, data=suite_data(custom_values={"orientation": "sea"}), room_numbers=[])
        assert ok.custom_values == {"orientation": "sea"}
        with pytest.raises(DomainError) as exc:
            provision_room_type(
                prop, data=suite_data(code="SUP", custom_values={"orientation": "moon"}), room_numbers=[]
            )
        assert exc.value.extra["fields"]["custom_values"] == {"orientation": ["Opción inválida: moon"]}


class TestSideEffects:
    def test_signals_inventory_changed_once_and_audits(
        self, prop, owner, catalog, django_capture_on_commit_callbacks
    ):
        received, stop = listen(inventory_changed)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                room_type = provision_room_type(
                    prop, data=suite_data(), room_numbers=["301", "302"], actor=owner
                )
        finally:
            stop()
        assert received == [{"property": prop, "room_type_ids": [room_type.pk], "start": None, "end": None}]
        event = AuditEvent.objects.get(action="inventory.room_type_provisioned")
        assert (event.target_id, event.actor, event.property) == (str(room_type.pk), owner, prop)
        assert "2" in event.summary

    def test_failures_signal_nothing(self, prop, django_capture_on_commit_callbacks):
        received, stop = listen(inventory_changed)
        try:
            with django_capture_on_commit_callbacks(execute=True), pytest.raises(DomainError):
                provision_room_type(prop, data=suite_data(kind="suite"), room_numbers=["301"])
        finally:
            stop()
        assert received == []


@pytest.mark.django_db(transaction=True)
class TestConcurrency:
    """Onboarding (C9) and signup (C11) may provision at the same time (double submit, retries): the second
    call must get a clean DomainError, never a raw IntegrityError, and nothing may be half created."""

    @staticmethod
    def race(calls, monkeypatch):
        import threading
        import time

        from django.db import connection

        from apps.inventory import services

        real_create_rooms = services._create_rooms

        def slow_create_rooms(*args, **kwargs):
            time.sleep(0.4)  # keeps the first transaction open while the second one validates
            return real_create_rooms(*args, **kwargs)

        monkeypatch.setattr(services, "_create_rooms", slow_create_rooms)
        barrier = threading.Barrier(len(calls))
        outcomes = []

        def worker(call):
            try:
                barrier.wait(timeout=10)
                outcomes.append(("created", call().code))
            except DomainError as exc:
                outcomes.append(("rejected", exc.code))
            except Exception as exc:  # noqa: BLE001 - reported by the assertions
                outcomes.append(("error", repr(exc)))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(call,)) for call in calls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return outcomes

    def test_the_same_category_twice_at_once_creates_it_once(self, prop, monkeypatch):
        def provision():
            return provision_room_type(prop, data=suite_data(amenities=[]), room_numbers=["301-303"])

        outcomes = self.race([provision, provision], monkeypatch)

        assert sorted(kind for kind, _ in outcomes) == ["created", "rejected"], outcomes
        assert RoomType.objects.filter(property=prop, code="STE").count() == 1
        assert Room.objects.filter(property=prop).count() == 3

    def test_overlapping_room_numbers_at_once_report_duplicates(self, prop, monkeypatch):
        calls = [
            lambda: provision_room_type(prop, data=suite_data(amenities=[]), room_numbers=["301-303"]),
            lambda: provision_room_type(
                prop, data=suite_data(code="SUP", amenities=[]), room_numbers=["303"]
            ),
        ]

        outcomes = self.race(calls, monkeypatch)

        assert sorted(outcomes) in (
            [("created", "STE"), ("rejected", "duplicate_room_numbers")],
            [("created", "SUP"), ("rejected", "duplicate_room_numbers")],
        ), outcomes
        assert Room.objects.filter(property=prop, number="303").count() == 1
