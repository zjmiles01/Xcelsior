"""Hand-picked micro taxonomy for the resume tests (same spirit as
micro_market.py): small enough that every expected skill match and title
resolution in the resume tests is hand-computable, real enough to
exercise the matcher's gates (Go is case-sensitive + context-gated).

Returns the software-engineer canonical title id, which the tests use to
assert experience canonicalization.
"""

from sqlalchemy.orm import Session

from app.catalog.taxonomy_models import (
    CanonicalTitle,
    Technology,
    TechnologyAlias,
    TitleAlias,
)

TECHS = [
    # (slug, name, category, case_sensitive, require_context, extra_aliases)
    ("python", "Python", "languages", False, False, []),
    ("go", "Go", "languages", True, True, []),
    ("typescript", "TypeScript", "languages", False, False, []),
    ("sql", "SQL", "databases", False, False, []),
    ("postgresql", "PostgreSQL", "databases", False, False, ["postgres"]),
    ("redis", "Redis", "databases", False, False, []),
    ("kafka", "Kafka", "messaging", False, False, []),
    ("docker", "Docker", "infrastructure", False, False, []),
    ("kubernetes", "Kubernetes", "infrastructure", False, False, ["k8s"]),
    ("aws", "AWS", "cloud", False, False, []),
    ("terraform", "Terraform", "infrastructure", False, False, []),
    ("flask", "Flask", "frameworks", False, False, []),
    ("fastapi", "FastAPI", "frameworks", False, False, []),
]

EXPECTED_ALEX_CHEN_SLUGS = {
    "python", "go", "typescript", "sql", "postgresql", "redis", "kafka",
    "docker", "kubernetes", "aws", "terraform", "flask", "fastapi",
}


def seed_micro_taxonomy(db: Session) -> int:
    for slug, name, category, case_sensitive, require_context, extra in TECHS:
        tech = Technology(slug=slug, name=name, category=category)
        db.add(tech)
        db.flush()
        db.add(
            TechnologyAlias(
                technology_id=tech.id,
                alias=name.lower(),
                cased=name,
                case_sensitive=case_sensitive,
                require_context=require_context,
            )
        )
        for alias in extra:
            db.add(
                TechnologyAlias(
                    technology_id=tech.id, alias=alias, cased=alias,
                    case_sensitive=False, require_context=False,
                )
            )
    se = CanonicalTitle(slug="software-engineer", name="Software Engineer")
    db.add(se)
    db.flush()
    db.add(TitleAlias(canonical_title_id=se.id, alias="software engineer"))
    db.add(TitleAlias(canonical_title_id=se.id, alias="backend engineer"))
    db.commit()
    return se.id
