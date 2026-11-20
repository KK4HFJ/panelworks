"""Small helpers shared by the MQTT and webhook layers."""

import os
import re

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand(value):
    """Replace ${VAR} or ${VAR:-default} with the environment variable, so
    secrets and per-site addresses stay out of the JSON you commit.
    Non-strings pass through unchanged."""
    if not isinstance(value, str):
        return value
    return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
