"""Imports every model module so Base.metadata is complete.

SQLAlchemy resolves relationships and foreign keys against the metadata
registry, which is populated as a side effect of imports. Any entrypoint
that touches the ORM (API, CLI, Alembic) must import this module first,
or cross-module foreign keys fail to resolve at flush time.
"""

import app.accounts.models  # noqa: F401
import app.analytics.models  # noqa: F401
import app.catalog.models  # noqa: F401
import app.catalog.taxonomy_models  # noqa: F401
import app.extraction.models  # noqa: F401
import app.ingestion.models  # noqa: F401
import app.profile.models  # noqa: F401
