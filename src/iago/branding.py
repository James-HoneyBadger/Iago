"""Single source of truth for product branding.

Renaming the product only requires editing this module (plus the package
directory name if the Python import name should change too).
"""

APP_NAME = "Iago"
APP_SLUG = "iago"
APP_TAGLINE = "Reversi, refined."
VERSION = "4.0.0"
COPYRIGHT = "© 2025 Honey Badger Universe"
DATA_DIR_NAME = "iago"
SAVE_FILE_EXTENSION = ".iago.json"

__all__ = [
    "APP_NAME",
    "APP_SLUG",
    "APP_TAGLINE",
    "VERSION",
    "COPYRIGHT",
    "DATA_DIR_NAME",
    "SAVE_FILE_EXTENSION",
]
