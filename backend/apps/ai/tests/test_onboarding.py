"""AI-assisted onboarding: the hotel's description (and website) → a normalized, editable proposal → `apply`
creates the room types, rooms, rates, extras and profile in one transaction."""

from decimal import Decimal

import httpx
import pytest
import respx

from apps.ai.onboarding import apply_proposal, fetch_website_text, normalize_proposal, propose
from apps.ai.tests.fakes import ScriptedLLM, real_data
from apps.core.errors import DomainError

pytestmark = pytest.mark.django_db

DESCRIPTION = (
    "Somos un hotel boutique de 4 estrellas en Cartagena, en el Centro Histórico. Tenemos 12 habitaciones: "
    "8 dobles a 280.000 la noche y 4 suites con vista al mar a 450.000. Desayuno por 30.000 por persona. "
    "Aceptamos mascotas. Check-in a las 3 pm y check-out a las 12. Tenemos piscina, wifi y aire "
    "acondicionado."
)


@pytest.fixture
def catalog(db):
    from apps.inventory.tests.factories import AmenityFactory

    return {
        code: AmenityFactory(code=code)
        for code in ("wifi", "pool", "air_conditioning", "sea_view", "breakfast", "parking", "tv")
    }


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr("apps.ai.onboarding.resolve_host", lambda host: ["93.184.216.34"])


def room_types_by_code(proposal):
    return {item["code"]: item for item in proposal["room_types"]}


# ---- website -----------------------------------------------------------------------------------------------


@respx.mock
def test_the_website_text_is_read_without_scripts_or_styles(public_dns):
    html = (
        "<html><head><title>Casa Mar</title><style>body{color:red}</style><script>var tracking = "
        "'secreto';</script></head><body><h1>Casa Mar</h1><p>Habitaciones con vista&nbsp;al mar &amp; "
        "desayuno.</p><noscript>activa js</noscript></body></html>"
    )
    respx.get("https://casamar.example/").mock(return_value=httpx.Response(200, html=html))

    site = fetch_website_text("https://casamar.example/")

    assert site["fetched"] is True
    assert "Habitaciones con vista al mar & desayuno." in site["text"]
    assert (
        "tracking" not in site["text"] and "color:red" not in site["text"] and "activa js" not in site["text"]
    )


@respx.mock
def test_the_website_text_is_capped_at_20k_characters(public_dns):
    respx.get("https://grande.example/").mock(
        return_value=httpx.Response(200, html=f"<p>{'hotel ' * 10000}</p>")
    )

    assert len(fetch_website_text("https://grande.example/")["text"]) == 20_000


@respx.mock
def test_private_addresses_are_never_fetched(monkeypatch):
    monkeypatch.setattr("apps.ai.onboarding.resolve_host", lambda host: ["127.0.0.1"])
    route = respx.get("http://intranet.example/")

    site = fetch_website_text("http://intranet.example/")

    assert site["fetched"] is False and site["error"]
    assert not route.called


def test_only_http_urls_are_fetched():
    assert fetch_website_text("file:///etc/passwd")["fetched"] is False


@respx.mock
def test_a_website_that_fails_does_not_stop_the_proposal(prop, catalog, public_dns, llm_mode):
    llm_mode("simulated")
    respx.get("https://caido.example/").mock(side_effect=httpx.ConnectTimeout("timeout"))

    result = propose(prop, description=DESCRIPTION, website_url="https://caido.example/")

    assert result["website"]["fetched"] is False
    assert result["proposal"]["room_types"]


# ---- proposal ----------------------------------------------------------------------------------------------


def test_the_offline_proposal_reads_rooms_prices_and_policies_from_the_description(prop, catalog, llm_mode):
    llm_mode("simulated")

    result = propose(prop, description=DESCRIPTION)

    assert result["simulated"] is True
    proposal = result["proposal"]
    types = {item["name"]["es"]: item for item in proposal["room_types"]}
    assert (types["Doble"]["units"], types["Doble"]["base_price"]) == (8, "280000")
    assert (types["Suite"]["units"], types["Suite"]["base_price"]) == (4, "450000")
    assert "sea_view" in types["Suite"]["amenities"]
    assert proposal["property"]["city"] == "Cartagena"
    assert (proposal["property"]["check_in_time"], proposal["property"]["check_out_time"]) == (
        "15:00",
        "12:00",
    )
    assert proposal["property"]["star_rating"] == 4
    assert proposal["policies"]["pets_allowed"] is True
    assert proposal["policies"]["breakfast_price"] == "30000"
    assert {"wifi", "pool", "air_conditioning"} <= set(proposal["property"]["amenities"])


def test_a_hostel_description_becomes_dorms_sold_by_bed(prop, catalog, llm_mode):
    llm_mode("simulated")

    proposal = propose(
        prop,
        description="Hostal en Bogotá con 2 dormitorios de 6 camas a 60.000 la cama y 3 "
        "habitaciones privadas a 150.000.",
    )["proposal"]

    dorm = next(item for item in proposal["room_types"] if item["kind"] == "dorm")
    assert (dorm["units"], dorm["beds_per_room"], dorm["base_price"]) == (2, 6, "60000")
    assert dorm["room_numbers"] == ["D1", "D2"]
    private = next(item for item in proposal["room_types"] if item["kind"] == "private")
    assert (private["units"], private["base_price"]) == (3, "150000")


def test_the_models_proposal_is_normalized_and_validated(prop, catalog):
    from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory

    RoomFactory(room_type=RoomTypeFactory(property=prop, code="STD"), number="101")
    raw = {
        "property": {"name": "", "city": "Medellín", "check_in_time": "3pm", "star_rating": 9},
        "room_types": [
            {
                "code": "std",
                "name_es": "Estándar",
                "name_en": "Standard",
                "kind": "private",
                "units": 3,
                "beds": [{"type": "Queen", "count": 1}],
                "amenities": ["wifi", "helipuerto"],
                "base_price": -5,
            },
            {
                "code": "STD",
                "name_es": "Estándar vista",
                "kind": "private",
                "units": 0,
                "max_occupancy": 3,
                "beds": [{"type": "litera", "count": 1}],
                "base_price": 320000,
                "weekend_adjust_percent": 15,
            },
            {
                "code": "",
                "name_es": "Dormitorio mixto",
                "kind": "dorm",
                "units": 1,
                "beds": [{"type": "bunk", "count": 4}],
                "base_price": 55000,
            },
        ],
        "policies": {"non_refundable_discount_percent": 150, "pets_allowed": "no"},
        "extras": [
            {"code": "park", "name_es": "Parqueadero", "price": 25000, "charge_type": "per_night"},
            {"code": "", "name_es": "Gratis", "price": 0, "charge_type": "per_stay"},
        ],
    }

    proposal, warnings = normalize_proposal(prop, raw)

    types = proposal["room_types"]
    assert [item["code"] for item in types] == ["STD2", "STD3", "DM"]  # unique in the hotel and the proposal
    first, second, dorm = types
    assert first["amenities"] == ["wifi"]
    assert first["base_price"] == "250000"  # invalid price → the default for its kind, with a warning
    assert first["room_numbers"] == ["102", "103", "104"]  # 101 already exists
    assert second["units"] == 1 and second["beds"] == [{"type": "bunk", "count": 1}]
    assert (second["max_occupancy"], second["max_children"]) == (3, 2)
    assert (dorm["kind"], dorm["beds_per_room"], dorm["room_numbers"]) == ("dorm", 8, ["D1"])
    assert proposal["property"]["name"] == prop.name
    assert proposal["property"]["check_in_time"] == "15:00"
    assert proposal["property"]["star_rating"] is None
    assert proposal["policies"]["non_refundable_discount_percent"] == 12
    assert [extra["code"] for extra in proposal["extras"]] == ["PARK"]
    assert any("helipuerto" in warning for warning in warnings)
    assert any("Estándar" in warning and "precio" in warning.lower() for warning in warnings)


def test_a_real_models_structured_answer_is_used(prop, catalog, monkeypatch):
    llm = ScriptedLLM(
        [
            real_data(
                {
                    "property": {"name": "Casa Azul", "city": "Santa Marta"},
                    "room_types": [
                        {
                            "code": "DBL",
                            "name_es": "Doble",
                            "name_en": "Double",
                            "kind": "private",
                            "units": 2,
                            "beds": [{"type": "double", "count": 1}],
                            "base_price": 200000,
                        }
                    ],
                    "policies": {},
                    "extras": [],
                }
            )
        ]
    )
    monkeypatch.setattr("apps.ai.onboarding.llm_for", lambda *args, **kwargs: llm)

    result = propose(prop, description="Casa Azul, 2 habitaciones dobles en Santa Marta")

    assert result["simulated"] is False
    assert room_types_by_code(result["proposal"])["DBL"]["base_price"] == "200000"
    call = llm.calls[0]
    assert call["response_schema"]["title"] == "onboarding_proposal"
    assert "Casa Azul, 2 habitaciones dobles en Santa Marta" in call["messages"][-1]["content"]
    assert "wifi" in call["system"]  # the valid amenity codes are given to the model


def test_a_description_or_a_website_is_required(prop):
    with pytest.raises(DomainError) as caught:
        propose(prop, description="  ", website_url="")

    assert caught.value.code == "validation_error"


# ---- apply -------------------------------------------------------------------------------------------------


def test_apply_creates_everything_in_one_go(prop, catalog, owner, llm_mode):
    from apps.inventory.models import Room, RoomType
    from apps.rates.models import Extra, RatePlan, RoomTypeRateDefaults, Tax

    llm_mode("simulated")
    proposal = propose(prop, description=DESCRIPTION)["proposal"]

    summary = apply_proposal(prop, proposal, actor=owner)

    types = {item.name["es"]: item for item in RoomType.objects.filter(property=prop)}
    assert set(types) == {"Doble", "Suite"}
    assert Room.objects.filter(room_type=types["Doble"]).count() == 8
    assert Room.objects.filter(room_type=types["Suite"]).count() == 4
    assert set(RatePlan.objects.filter(property=prop).values_list("code", flat=True)) == {"FLEX", "NR", "BB"}
    assert RatePlan.objects.get(property=prop, code="BB").derivation_value == Decimal("30000")
    flex = RatePlan.objects.get(property=prop, code="FLEX")
    assert RoomTypeRateDefaults.objects.get(room_type=types["Suite"], rate_plan=flex).price == Decimal(
        "450000"
    )
    assert Tax.objects.filter(property=prop, code="IVA").exists()
    assert Extra.objects.filter(property=prop, code="BRK", price=Decimal("30000")).exists()
    prop.refresh_from_db()
    assert (prop.city, prop.check_in_time.strftime("%H:%M")) == ("Cartagena", "15:00")
    assert prop.settings["policies"]["pets_allowed"] is True
    assert summary["rooms_created"] == 12
    assert {item["code"] for item in summary["room_types"]} == {
        item["code"] for item in proposal["room_types"]
    }


def test_apply_is_all_or_nothing(prop, catalog, owner):
    from apps.inventory.models import RoomType
    from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
    from apps.rates.models import RatePlan

    RoomFactory(room_type=RoomTypeFactory(property=prop, code="OLD"), number="201")
    proposal, _ = normalize_proposal(
        prop,
        {
            "room_types": [
                {"code": "DBL", "name_es": "Doble", "kind": "private", "units": 2, "base_price": 200000},
                {"code": "STE", "name_es": "Suite", "kind": "private", "units": 1, "base_price": 400000},
            ],
        },
    )
    proposal["room_types"][1]["room_numbers"] = ["201"]  # edited by hand to a number that exists

    with pytest.raises(DomainError) as caught:
        apply_proposal(prop, proposal, actor=owner)

    assert caught.value.code == "duplicate_room_numbers"
    assert list(RoomType.objects.filter(property=prop).values_list("code", flat=True)) == ["OLD"]
    assert not RatePlan.objects.filter(property=prop).exists()


def test_apply_needs_at_least_one_room_type(prop, owner):
    with pytest.raises(DomainError):
        apply_proposal(prop, {"room_types": []}, actor=owner)


# ---- API ---------------------------------------------------------------------------------------------------


def test_the_onboarding_api_proposes_and_applies(prop, catalog, api, llm_mode):
    from apps.inventory.models import RoomType

    llm_mode("simulated")

    proposed = api.post("/api/v1/ai/onboarding/propose/", {"description": DESCRIPTION}, format="json")

    assert proposed.status_code == 200, proposed.json()
    proposal = proposed.json()["proposal"]
    applied = api.post("/api/v1/ai/onboarding/apply/", {"proposal": proposal}, format="json")
    assert applied.status_code == 201, applied.json()
    assert applied.json()["rooms_created"] == 12
    assert RoomType.objects.filter(property=prop).count() == 2


def test_the_onboarding_api_reports_what_is_wrong(prop, catalog, api):
    from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory

    RoomFactory(room_type=RoomTypeFactory(property=prop, code="OLD"), number="101")
    proposal = {
        "room_types": [
            {
                "code": "DBL",
                "name": {"es": "Doble", "en": "Double"},
                "kind": "private",
                "units": 1,
                "room_numbers": ["101"],
                "base_price": "200000",
            }
        ]
    }

    response = api.post("/api/v1/ai/onboarding/apply/", {"proposal": proposal}, format="json")

    assert (response.status_code, response.json()["code"]) == (400, "duplicate_room_numbers")


def test_front_desk_cannot_use_the_onboarding(prop, make_member, api_for):
    client = api_for(make_member("front_desk"), prop)

    response = client.post("/api/v1/ai/onboarding/propose/", {"description": DESCRIPTION}, format="json")

    assert (response.status_code, response.json()["permission"]) == (403, "ai.onboarding")
