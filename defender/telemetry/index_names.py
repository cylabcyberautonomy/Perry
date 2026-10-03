"""Per-experiment Elasticsearch index names, scoped so concurrent runs do not mix telemetry."""

import re

FALCO_BASE = "falco"
SYSFLOW_BASE = "sysflow"


def sanitize(experiment_name: str) -> str:
    """Reduce an experiment name to characters Elasticsearch accepts in an index name."""
    slug = re.sub(r"[^a-z0-9_.-]+", "-", experiment_name.strip().lower())
    slug = slug.strip("-_+.")
    return slug


def scoped_index(base: str, experiment_name: str | None) -> str:
    """`base` scoped to one experiment, or `base` unchanged when no experiment name is available."""
    if not experiment_name:
        return base
    slug = sanitize(experiment_name)
    if not slug:
        return base
    # 255 bytes is ES's index-name limit.
    return f"{base}-{slug}"[:255]


def falco_index(experiment_name: str | None) -> str:
    return scoped_index(FALCO_BASE, experiment_name)


def sysflow_index(experiment_name: str | None) -> str:
    return scoped_index(SYSFLOW_BASE, experiment_name)
