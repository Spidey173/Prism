"""Create a small text-layer PDF containing known auditor findings (stdlib only)."""

from pathlib import Path


def _text(x: int, y: int, value: str, size: int = 11) -> str:
    safe = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 {size} Tf {x} {y} Td ({safe}) Tj ET\n"


def _page(content: str) -> bytes:
    stream = content.encode("ascii")
    return b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream"


def create_pdf() -> Path:
    pages = []
    first = "".join([
        _text(54, 740, "Auditor Phase 2 planted-error fixture", 16),
        _text(54, 700, "Acme reported revenue of $1.5M in FY2025."),
        _text(54, 680, "Later, Acme reported revenue of $1.2M in FY2025."),
        _text(54, 640, "Acme prior revenue was 100; current revenue is 120; revenue growth is 30%."),
        _text(54, 590, "Project start date: May 1, 2025."),
        _text(54, 570, "Project end date: April 30, 2025."),
    ])
    pages.append(_page(first))

    table = ""
    xs = [54, 250, 390, 520]
    ys = [730, 700, 670, 640, 610]
    for x in xs:
        table += f"{x} 610 m {x} 730 l S\n"
    for y in ys:
        table += f"54 {y} m 520 {y} l S\n"
    table += "".join([
        _text(64, 710, "Region"), _text(260, 710, "Revenue"),
        _text(64, 680, "North"), _text(260, 680, "40"),
        _text(64, 650, "South"), _text(260, 650, "50"),
        _text(64, 620, "Total"), _text(260, 620, "100"),
    ])
    pages.append(_page(table))

    semantic_left = "".join([
        _text(54, 740, "Service agreement terms", 16),
        _text(54, 700, "The service agreement may be renewed at the end of every annual term."),
        _text(54, 675, "The supplier must give written notice before terminating the service agreement."),
        _text(54, 650, "The support plan renews automatically at each monthly anniversary."),
        _text(54, 625, "The insurance policy covers accidental water damage to the property."),
    ])
    pages.append(_page(semantic_left))

    semantic_right = "".join([
        _text(54, 740, "Additional agreement terms", 16),
        _text(54, 700, "The service agreement cannot be renewed after the initial term."),
        _text(54, 675, "The supplier may terminate the service agreement without giving any prior notice."),
        _text(54, 650, "The customer may cancel the support plan at any time without penalty."),
        _text(54, 625, "The insurance policy excludes intentional water damage from coverage."),
    ])
    pages.append(_page(semantic_right))

    objects: list[bytes] = []
    # Object numbers: catalog, pages tree, font, then page/content pairs.
    page_ids = [4 + index * 2 for index in range(len(pages))]
    content_ids = [page_id + 1 for page_id in page_ids]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.extend([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ])
    for page_id, content_id, stream in zip(page_ids, content_ids, pages, strict=True):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        objects.append(stream)

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    output = Path(__file__).with_name("phase2_planted_errors.pdf")
    output.write_bytes(pdf)
    return output


if __name__ == "__main__":
    print(create_pdf())
