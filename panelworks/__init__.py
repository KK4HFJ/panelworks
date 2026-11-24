"""PanelWorks - draw a form in JSON, write event procedures in Python, and
drive every object live over MCP (agents) and MQTT (devices)."""

__version__ = "1.0.0"

from .runtime import Form, load_form, CONTROL_TYPES  # noqa: F401,E402
