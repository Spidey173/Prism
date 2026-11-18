from pathlib import Path

import fitz


def main() -> None:
    output = Path(__file__).with_name("sample_report.pdf")
    document = fitz.open()

    first = document.new_page(width=612, height=792)
    first.insert_text((54, 64), "Sample report: quarterly results.", fontsize=18)
    first.insert_text((54, 120), "Fig. 3 shows Acme Inc. revenue of $1.5M, e.g., in the first quarter.")
    first.insert_text((54, 145), "The report states growth of 12.5%. The final count is 12.")
    first.insert_text((54, 210), "This sentence begins near the bottom of this page and continues", fontsize=12)

    second = document.new_page(width=612, height=792)
    second.insert_text((54, 64), "on the next page before it ends.", fontsize=12)
    document.new_page(width=612, height=792)  # A deliberately empty page.

    document.save(output)
    document.close()
    print(output)


if __name__ == "__main__":
    main()
