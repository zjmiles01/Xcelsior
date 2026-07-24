"""Taxonomy loading and the in-memory index the extractors run against.

The YAML files under data/taxonomy/ are the reviewable source of truth;
`load-taxonomy` syncs them into the database, and the runtime index can be
built from either source (YAML for pure/offline use like the gold-set eval,
database rows for the live pipeline)."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_TAXONOMY_DIR = Path(__file__).resolve().parents[3] / "data" / "taxonomy"

CATEGORIES = frozenset({
    "languages", "frameworks", "cloud", "infrastructure", "databases",
    "testing", "messaging", "data_engineering", "ai_ml", "security",
})

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")


@dataclass(frozen=True)
class AliasSpec:
    alias: str  # lowercased form used by the automaton
    cased: str  # original casing, checked when case_sensitive
    tech_slug: str
    case_sensitive: bool = False
    require_context: bool = False


@dataclass(frozen=True)
class TechSpec:
    slug: str
    name: str
    category: str


@dataclass(frozen=True)
class TitleSpec:
    slug: str
    name: str


@dataclass
class TaxonomyIndex:
    technologies: dict[str, TechSpec] = field(default_factory=dict)
    aliases: list[AliasSpec] = field(default_factory=list)
    titles: dict[str, TitleSpec] = field(default_factory=dict)
    title_aliases: dict[str, str] = field(default_factory=dict)  # normalized alias -> title slug


def _parse_alias(entry: str | dict, tech_slug: str) -> AliasSpec:
    if isinstance(entry, str):
        return AliasSpec(alias=entry.lower(), cased=entry, tech_slug=tech_slug)
    cased = str(entry["alias"])
    return AliasSpec(
        alias=cased.lower(),
        cased=cased,
        tech_slug=tech_slug,
        case_sensitive=bool(entry.get("case_sensitive", False)),
        require_context=bool(entry.get("require_context", False)),
    )


def load_index(taxonomy_dir: Path = DEFAULT_TAXONOMY_DIR) -> TaxonomyIndex:
    index = TaxonomyIndex()

    tech_doc = yaml.safe_load((taxonomy_dir / "technologies.yaml").read_text())
    for entry in tech_doc["technologies"]:
        name = entry["name"]
        slug = entry.get("slug") or slugify(name)
        category = entry["category"]
        if category not in CATEGORIES:
            raise ValueError(f"unknown category {category!r} for {name!r}")
        if slug in index.technologies:
            raise ValueError(f"duplicate technology slug {slug!r}")
        index.technologies[slug] = TechSpec(slug=slug, name=name, category=category)

        match_flags = entry.get("match") or {}
        index.aliases.append(
            AliasSpec(
                alias=name.lower(),
                cased=name,
                tech_slug=slug,
                case_sensitive=bool(match_flags.get("case_sensitive", False)),
                require_context=bool(match_flags.get("require_context", False)),
            )
        )
        for raw_alias in entry.get("aliases") or []:
            index.aliases.append(_parse_alias(raw_alias, slug))

    title_doc = yaml.safe_load((taxonomy_dir / "titles.yaml").read_text())
    for entry in title_doc["titles"]:
        slug = entry["slug"]
        index.titles[slug] = TitleSpec(slug=slug, name=entry["name"])
        index.title_aliases[entry["name"].lower()] = slug
        for alias in entry.get("aliases") or []:
            index.title_aliases[alias.lower()] = slug

    return index
