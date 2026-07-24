"""Regenerates the committed resume fixture PDFs. Dev-only (needs fpdf2).

The committed PDFs are the fixtures of record — tests read them, never
this script — so CI needs no PDF writer. Re-run only when fixture content
must change, and re-verify the tests' expected values afterwards:

    uv run python tests/fixtures/resumes/generate_fixtures.py

ASCII only: the core-font fixtures should exercise the parser, not
font-encoding edge cases (unicode normalization is covered by the pure
text tests, which need no PDF at all).
"""

from pathlib import Path

from fpdf import FPDF

HERE = Path(__file__).parent

# Known-truth resume: single column, the format the deterministic parser
# targets. Every technology named here exists in data/taxonomy/.
ALEX_CHEN_LINES = [
    "Alex Chen",
    "San Francisco, CA | alex.chen@example.com | (415) 555-0100",
    "",
    "Summary",
    "Backend engineer with 6 years building distributed systems in Python and Go.",
    "",
    "Skills",
    "Languages: Python, Go, TypeScript, SQL",
    "Infrastructure: PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS, Terraform",
    "",
    "Experience",
    "",
    "Senior Software Engineer, Wavelength Analytics",
    "Mar 2022 - Present",
    "- Designed a Kafka-based event pipeline processing 40M events per day.",
    "- Led migration of the core API from Flask to FastAPI on Kubernetes.",
    "",
    "Software Engineer, Harborview Systems",
    "Jul 2019 - Feb 2022",
    "- Built PostgreSQL-backed billing services in Python.",
    "- Introduced Terraform modules for AWS infrastructure.",
    "",
    "Backend Engineer Intern, Northstar Labs",
    "Jun 2018 - Aug 2018",
    "- Prototyped a Go microservice for log ingestion.",
    "",
    "Education",
    "",
    "University of California, Berkeley",
    "B.S. in Computer Science, 2015 - 2019",
]


def _write_lines(pdf: FPDF, lines: list[str]) -> None:
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")


def main() -> None:
    resume = FPDF()
    resume.add_page()
    _write_lines(resume, ALEX_CHEN_LINES)
    (HERE / "alex_chen.pdf").write_bytes(bytes(resume.output()))

    blank = FPDF()
    blank.add_page()
    (HERE / "blank.pdf").write_bytes(bytes(blank.output()))

    encrypted = FPDF()
    encrypted.add_page()
    _write_lines(encrypted, ALEX_CHEN_LINES[:2])
    encrypted.set_encryption(owner_password="owner-secret", user_password="user-secret")
    (HERE / "encrypted.pdf").write_bytes(bytes(encrypted.output()))

    print(f"wrote fixtures to {HERE}")


if __name__ == "__main__":
    main()
