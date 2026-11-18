from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import fitz
import pysbd  # type: ignore[import-untyped]


class ScannedPdfError(ValueError):
    """Raised when a PDF has pages but no extractable text layer."""


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    width: float
    height: float
    text: str


@dataclass(frozen=True)
class ParsedSegment:
    sentence_id: uuid.UUID
    segment_index: int
    page_number: int
    text: str
    bboxes: list[list[float]]
    chunk_type: str = "sentence"
    table_cells: list[dict[str, Any]] = field(default_factory=list)
    table_bbox: list[float] | None = None
    header_row: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    pages: list[ParsedPage]
    segments: list[ParsedSegment]


@dataclass(frozen=True)
class _Word:
    text: str
    page_number: int
    block_no: int
    line_no: int
    word_no: int
    start: int
    end: int
    bbox: fitz.Rect


@dataclass(frozen=True)
class _PageData:
    page: ParsedPage
    words: list[_Word]


def _normalize_rect(rect: fitz.Rect, width: float, height: float) -> list[float]:
    return [
        round(min(1.0, max(0.0, rect.x0 / width)), 6),
        round(min(1.0, max(0.0, rect.y0 / height)), 6),
        round(min(1.0, max(0.0, rect.x1 / width)), 6),
        round(min(1.0, max(0.0, rect.y1 / height)), 6),
    ]


def _build_page(
    page: fitz.Page,
    page_number: int,
    global_offset: int,
    table_rects: list[fitz.Rect],
) -> _PageData:
    raw_words = sorted(
        page.get_text("words", sort=False),
        key=lambda item: (int(item[5]), int(item[6]), int(item[7])),
    )
    parts: list[str] = []
    words: list[_Word] = []
    local_offset = 0
    previous: tuple[int, int] | None = None
    for item in raw_words:
        x0, y0, x1, y1, raw_text, block_no, line_no, word_no = item[:8]
        raw_rect = fitz.Rect(x0, y0, x1, y1)
        word_center = fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if any(table_rect.contains(word_center) for table_rect in table_rects):
            continue
        token = str(raw_text).strip()
        if not token:
            continue
        line_key = (int(block_no), int(line_no))
        if previous is not None:
            separator = " " if previous == line_key else "\n\n" if previous[0] != line_key[0] else "\n"
            parts.append(separator)
            local_offset += len(separator)
        start = local_offset
        parts.append(token)
        local_offset += len(token)
        # Text coordinates are in the unrotated page space. Transform both the
        # rectangle and its dimensions into the same rotated page.rect space.
        rect = fitz.Rect(x0, y0, x1, y1) * page.rotation_matrix
        words.append(
            _Word(
                text=token,
                page_number=page_number,
                block_no=int(block_no),
                line_no=int(line_no),
                word_no=int(word_no),
                start=global_offset + start,
                end=global_offset + local_offset,
                bbox=rect,
            )
        )
        previous = line_key

    page_text = "".join(parts)
    return _PageData(
        page=ParsedPage(
            page_number=page_number,
            width=page.rect.width,
            height=page.rect.height,
            text=page_text,
        ),
        words=words,
    )


def _extract_page_tables(page: fitz.Page, page_number: int) -> tuple[list[fitz.Rect], list[ParsedSegment]]:
    try:
        finder = page.find_tables()
    except Exception:
        finder = None

    if not finder or not finder.tables:
        try:
            # Fallback strategy for borderless or loose tables
            finder = page.find_tables(strategy="lines_strict")
        except Exception:
            pass

    excluded_rects: list[fitz.Rect] = []
    segments: list[ParsedSegment] = []
    if not finder:
        return excluded_rects, segments

    for table_index, table in enumerate(finder.tables):
        raw_table_rect = fitz.Rect(table.bbox)
        excluded_rects.append(raw_table_rect)
        rotated_table_rect = raw_table_rect * page.rotation_matrix
        table_bbox = _normalize_rect(rotated_table_rect, page.rect.width, page.rect.height)
        extracted_rows = table.extract()
        cells: list[dict[str, Any]] = []
        table_rows = table.rows
        for row_index, row_values in enumerate(extracted_rows):
            row = table_rows[row_index] if row_index < len(table_rows) else None
            row_cells = row.cells if row is not None else []
            for column_index, value in enumerate(row_values):
                cell_rect_data = row_cells[column_index] if column_index < len(row_cells) else None
                if cell_rect_data is None:
                    cell_bbox = table_bbox
                else:
                    cell_rect = fitz.Rect(cell_rect_data) * page.rotation_matrix
                    cell_bbox = _normalize_rect(cell_rect, page.rect.width, page.rect.height)
                cells.append(
                    {
                        "row": row_index,
                        "col": column_index,
                        "text": str(value or "").strip(),
                        "bbox": cell_bbox,
                    }
                )

        header_row: int | None = None
        if extracted_rows and extracted_rows[0]:
            first_row = [str(value or "").strip() for value in extracted_rows[0]]
            nonnumeric_headers = sum(not any(char.isdigit() for char in value) for value in first_row if value)
            nonempty_headers = sum(bool(value) for value in first_row)
            if nonempty_headers and nonnumeric_headers >= (nonempty_headers + 1) // 2:
                header_row = 0
                # Detect multi-line headers (e.g. Row 0: Section, Row 1: Years/Quarters/Dates)
                if len(extracted_rows) > 1 and extracted_rows[1]:
                    second_row = [str(value or "").strip() for value in extracted_rows[1]]
                    nonempty_second = sum(bool(value) for value in second_row)
                    has_date_or_header_words = any(
                        any(w in val.lower() for w in ("202", "201", "q1", "q2", "q3", "q4", "month", "ended", "period", "fy"))
                        for val in second_row if val
                    )
                    if nonempty_second and (not second_row[0] or has_date_or_header_words):
                        header_row = 1

        table_text = "\n".join(" | ".join(str(value or "").strip() for value in row) for row in extracted_rows)
        segments.append(
            ParsedSegment(
                sentence_id=uuid.uuid5(uuid.NAMESPACE_URL, f"table:{page_number}:{table_index}:{table_bbox}"),
                segment_index=0,
                page_number=page_number,
                text=table_text,
                bboxes=[table_bbox],
                chunk_type="table",
                table_cells=cells,
                table_bbox=table_bbox,
                header_row=header_row,
            )
        )
    return excluded_rects, segments


def parse_pdf(data: bytes, max_pages: int = 500) -> ParsedDocument:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except (fitz.FileDataError, ValueError) as exc:
        raise ValueError("The uploaded file is not a readable PDF.") from exc

    with document:
        if document.page_count > max_pages:
            raise ValueError(f"This PDF has {document.page_count} pages; the limit is {max_pages}.")

        page_data: list[_PageData] = []
        table_segments: list[ParsedSegment] = []
        global_parts: list[str] = []
        global_offset = 0
        for page_index, page in enumerate(document):
            if page_index:
                global_parts.append("\n\n")
                global_offset += 2
            table_rects, page_tables = _extract_page_tables(page, page_index + 1)
            result = _build_page(page, page_index + 1, global_offset, table_rects)
            page_data.append(result)
            global_parts.append(result.page.text)
            global_offset += len(result.page.text)
            table_segments.extend(page_tables)

        if not any(page.words for page in page_data) and not table_segments:
            raise ScannedPdfError(
                "This PDF has no selectable text. It may be scanned; OCR is not available yet."
            )

        document_text = "".join(global_parts)
        segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)
        sentence_spans = segmenter.segment(document_text)
        segments = []

        for span in sentence_spans:
            start, end = span.start, span.end
            while start < end and document_text[start].isspace():
                start += 1
            while end > start and document_text[end - 1].isspace():
                end -= 1
            if start == end:
                continue
            selected = [word for page in page_data for word in page.words if word.start < end and word.end > start]
            if not selected:
                continue

            per_page: dict[int, list[_Word]] = {}
            for word in selected:
                per_page.setdefault(word.page_number, []).append(word)
            sentence_id = uuid.uuid4()
            sentence_text = document_text[start:end]
            for segment_index, (page_number, page_words) in enumerate(per_page.items()):
                page = page_data[page_number - 1].page
                line_rects: dict[tuple[int, int], fitz.Rect] = {}
                for word in page_words:
                    key = (word.block_no, word.line_no)
                    if key in line_rects:
                        line_rects[key] |= word.bbox
                    else:
                        line_rects[key] = fitz.Rect(word.bbox)
                bboxes = [_normalize_rect(rect, page.width, page.height) for rect in line_rects.values()]
                segments.append(
                    ParsedSegment(
                        sentence_id=sentence_id,
                        segment_index=segment_index,
                        page_number=page_number,
                        text=sentence_text,
                        bboxes=bboxes,
                    )
                )

        segments.extend(table_segments)
        return ParsedDocument(pages=[page.page for page in page_data], segments=segments)
