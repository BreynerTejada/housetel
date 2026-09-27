"""Room-number ranges for bulk creation ("101-110,201,203") and floor inference."""

import pytest

from apps.core.errors import DomainError
from apps.inventory.numbering import MAX_ROOMS_PER_REQUEST, duplicates_in, infer_floor, parse_room_numbers


class TestParseRoomNumbers:
    def test_expands_ranges_and_keeps_singles_in_order(self):
        assert parse_room_numbers("101-103,105") == ["101", "102", "103", "105"]

    def test_accepts_spaces_semicolons_and_new_lines(self):
        assert parse_room_numbers(" 201 - 202 ;\n301,  302 ") == ["201", "202", "301", "302"]

    def test_keeps_zero_padding_and_letter_prefixes(self):
        assert parse_room_numbers("01-03") == ["01", "02", "03"]
        assert parse_room_numbers("A8-A10") == ["A8", "A9", "A10"]
        assert parse_room_numbers("B1-3") == ["B1", "B2", "B3"]

    def test_labels_that_are_not_ranges_are_taken_literally(self):
        assert parse_room_numbers("Suite Mar,PH-1,D1") == ["Suite Mar", "PH-1", "D1"]

    def test_accepts_a_list_of_numbers_or_ranges(self):
        assert parse_room_numbers(["101", " 102 ", "201-202"]) == ["101", "102", "201", "202"]

    def test_list_items_may_hold_several_parts(self):
        assert parse_room_numbers(["101-102,201", "301;302"]) == ["101", "102", "201", "301", "302"]

    def test_duplicates_are_returned_so_the_caller_can_report_them(self):
        assert parse_room_numbers("101-102,102") == ["101", "102", "102"]

    @pytest.mark.parametrize(
        "spec",
        [
            "",
            " , ",
            "110-101",  # reversed
            "A1-B3",  # different prefixes
            "12345678901234567890X",  # longer than Room.number (20)
            [],
            None,
        ],
    )
    def test_rejects_invalid_specs(self, spec):
        with pytest.raises(DomainError) as exc:
            parse_room_numbers(spec)
        assert exc.value.code == "invalid_room_numbers"

    def test_rejects_more_rooms_than_the_request_limit(self):
        with pytest.raises(DomainError) as exc:
            parse_room_numbers(f"1-{MAX_ROOMS_PER_REQUEST + 1}")
        assert exc.value.code == "invalid_room_numbers"
        assert len(parse_room_numbers(f"1-{MAX_ROOMS_PER_REQUEST}")) == MAX_ROOMS_PER_REQUEST

    def test_the_error_names_the_invalid_part(self):
        with pytest.raises(DomainError) as exc:
            parse_room_numbers("101-103,120-110")
        assert "120-110" in exc.value.message


def test_duplicates_in_lists_each_repeated_number_once_in_order():
    assert duplicates_in(["101", "102", "101", "103", "102", "101"]) == ["101", "102"]
    assert duplicates_in(["101", "102"]) == []


@pytest.mark.parametrize(
    ("number", "floor"),
    [("101", "1"), ("305", "3"), ("1203", "12"), ("A204", "2"), ("12", ""), ("Suite Mar", ""), ("D1", "")],
)
def test_infer_floor_uses_the_hotel_convention(number, floor):
    assert infer_floor(number) == floor
