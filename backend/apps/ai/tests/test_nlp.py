"""Text helpers of the offline assistant: dates, party size, codes, rooms, language and extractive answers."""

from datetime import date

import pytest

from apps.ai import nlp

TODAY = date(2026, 10, 1)  # Thursday


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("¿Tienen habitación del 12 al 14 de octubre para 2 personas?", ("2026-10-12", "2026-10-14")),
        ("Do you have a room from October 12 to October 15?", ("2026-10-12", "2026-10-15")),
        ("del 30 de octubre al 2 de noviembre", ("2026-10-30", "2026-11-02")),
        ("entre el 5 y el 8 de diciembre", ("2026-12-05", "2026-12-08")),
        ("para mañana por 2 noches", ("2026-10-02", "2026-10-04")),
        ("¿hay algo para hoy?", ("2026-10-01", "2026-10-02")),
        ("esta noche", ("2026-10-01", "2026-10-02")),
        ("pasado mañana", ("2026-10-03", "2026-10-04")),
        ("este fin de semana", ("2026-10-02", "2026-10-04")),
        ("this weekend please", ("2026-10-02", "2026-10-04")),
        ("2026-11-20 al 2026-11-23", ("2026-11-20", "2026-11-23")),
        ("20/11 al 23/11", ("2026-11-20", "2026-11-23")),
        ("el 3 de enero", ("2027-01-03", "2027-01-04")),
        ("on Oct 5 for 2 nights", ("2026-10-05", "2026-10-07")),
        ("llegan el 12 de octubre", ("2026-10-12", "2026-10-13")),
        ("12 al 14 oct", ("2026-10-12", "2026-10-14")),
        ("October 12-14", ("2026-10-12", "2026-10-14")),
        ("desde el viernes hasta el domingo", ("2026-10-02", "2026-10-04")),
        ("tomorrow for one night", ("2026-10-02", "2026-10-03")),
        ("del 28 de diciembre al 3 de enero", ("2026-12-28", "2027-01-03")),
        ("12-14 de octubre, 2 adultos", ("2026-10-12", "2026-10-14")),
        ("¿Tienen parqueadero?", None),
        ("del 14 al 12 de octubre", None),
    ],
)
def test_stay_dates(text, expected):
    found = nlp.stay_dates(text, TODAY)
    assert (tuple(d.isoformat() for d in found) if found else None) == expected


@pytest.mark.parametrize(
    ("text", "adults", "children"),
    [
        ("para 2 personas", 2, 0),
        ("somos 3 adultos y 1 niño", 3, 1),
        ("for two people", 2, 0),
        ("2 adults and 2 kids", 2, 2),
        ("dos adultos", 2, 0),
        ("una habitación", None, 0),
    ],
)
def test_party(text, adults, children):
    assert nlp.party(text) == (adults, children)


def test_reservation_codes_are_found_in_any_case():
    assert nlp.reservation_codes("saldo de ht-7k2m9q y HT-ABC234?") == ["HT-7K2M9Q", "HT-ABC234"]


@pytest.mark.parametrize(
    ("text", "room"),
    [
        ("mueve HT-7K2M9Q a la habitación 205", "205"),
        ("move it to room 301", "301"),
        ("bloquea la hab. 12B mañana", "12B"),
        ("pásalo a la 104", "104"),
        ("sin habitación", None),
    ],
)
def test_room_number(text, room):
    assert nlp.room_number(text) == room


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("¿Tienen habitaciones libres?", "es"),
        ("Do you have rooms available?", "en"),
        ("Hola", "es"),
        ("Hello there", "en"),
        ("Room for 2 on Oct 12", "en"),
        ("", "es"),
    ],
)
def test_language(text, language):
    assert nlp.language(text) == language


FAQ = [
    "¿Tienen parqueadero? → Sí, parqueadero cubierto por 25.000 la noche.",
    "¿Aceptan mascotas? → Sí, mascotas pequeñas con un cargo de 30.000 por estadía.",
    "Horarios: check-in desde las 15:00 y check-out hasta las 12:00.",
    "¿Cómo llegar? → Estamos a 15 minutos del aeropuerto, en el Centro Histórico.",
]


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("¿Puedo llevar a mi perro?", "Sí, mascotas pequeñas con un cargo de 30.000 por estadía."),
        ("hay estacionamiento para el carro?", "Sí, parqueadero cubierto por 25.000 la noche."),
        ("¿A qué hora es el check in?", "Horarios: check-in desde las 15:00 y check-out hasta las 12:00."),
        ("¿Dónde están ubicados?", "Estamos a 15 minutos del aeropuerto, en el Centro Histórico."),
        ("¿Cuál es la capital de Francia?", None),
    ],
)
def test_best_answer_extracts_the_matching_knowledge_line(question, answer):
    assert nlp.best_answer(question, FAQ) == answer
