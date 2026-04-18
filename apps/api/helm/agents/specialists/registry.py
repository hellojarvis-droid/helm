"""Import side-effect: register every specialist.

Importing this module pulls in every specialist file, which triggers their
`register()` calls at module load. Anyone who wants the full registry populated
should `import helm.agents.specialists.registry`.
"""

from __future__ import annotations

from helm.agents.specialists import (  # noqa: F401 — import-for-side-effect
    ads_operator,
    creative_director,
    customer_service,
    growth_analyst,
    idea_scout,
    product_builder,
    social_engagement,
    stubs,
)
