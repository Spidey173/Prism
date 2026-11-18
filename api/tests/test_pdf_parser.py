from __future__ import annotations

import fitz
import pytest

from app.services.pdf_parser import ScannedPdfError, parse_pdf


def make_pdf(pages: list[list[tuple[str, float, float]]], rotations: dict[int, int] | None = None) -> bytes:
    document = fitz.open()
    for page_index, entries in enumerate(pages):
        page = document.new_page(width=612, height=792)
        for text, x, y in entries:
            page.insert_text((x, y), text, fontsize=12)
        if rotations and page_index in rotations:
            page.set_rotation(rotations[page_index])
    result = document.tobytes()
    document.close()
    return result


def test_sentence_boundaries_cover_abbreviations_numbers_and_currency() -> None:
    pdf = make_pdf(
        [[
            ("Fig. 3 shows Acme Inc. revenue of $1.5M, e.g., the first quarter.", 50, 50),
            ("It grew by 12.5%.", 50, 75),
            ("The final count is 12.", 50, 100),
        ]]
    )

    parsed = parse_pdf(pdf)
    sentence_texts = list(dict.fromkeys(segment.text for segment in parsed.segments))

    assert len(sentence_texts) == 3
    assert sentence_texts[0].startswith("Fig. 3 shows Acme Inc. revenue of $1.5M, e.g.,")
    assert sentence_texts[1] == "It grew by 12.5%."
    assert sentence_texts[2] == "The final count is 12."


def test_bbox_values_are_normalized_and_merge_per_line() -> None:
    pdf = make_pdf([[("This sentence stays on the first line", 50, 50), ("and continues on a second line.", 50, 75)]])

    parsed = parse_pdf(pdf)
    segment = parsed.segments[0]

    assert len(segment.bboxes) == 2
    assert all(0 <= value <= 1 for bbox in segment.bboxes for value in bbox)
    assert all(bbox[0] < bbox[2] and bbox[1] < bbox[3] for bbox in segment.bboxes)


def test_sentence_crossing_page_boundary_has_page_local_segments() -> None:
    pdf = make_pdf(
        [
            [("A sentence begins on page one and continues", 50, 50)],
            [("on page two before it ends.", 50, 50)],
        ]
    )

    parsed = parse_pdf(pdf)
    matching = [segment for segment in parsed.segments if "A sentence begins" in segment.text]

    assert len(matching) == 2
    assert matching[0].sentence_id == matching[1].sentence_id
    assert {segment.page_number for segment in matching} == {1, 2}
    assert {segment.segment_index for segment in matching} == {0, 1}


def test_rotated_page_boxes_use_rotated_page_rect() -> None:
    parsed = parse_pdf(make_pdf([[("Rotated sentence ends here.", 50, 50)]], rotations={0: 90}))

    assert parsed.pages[0].width == 792
    assert parsed.pages[0].height == 612
    assert all(0 <= value <= 1 for box in parsed.segments[0].bboxes for value in box)


def test_empty_pages_are_preserved() -> None:
    parsed = parse_pdf(make_pdf([[("Text is present.", 50, 50)], []]))

    assert len(parsed.pages) == 2
    assert parsed.pages[1].text == ""
    assert parsed.pages[1].page_number == 2


def test_pdf_without_text_layer_is_rejected() -> None:
    with pytest.raises(ScannedPdfError, match="no selectable text"):
        parse_pdf(make_pdf([[]]))
