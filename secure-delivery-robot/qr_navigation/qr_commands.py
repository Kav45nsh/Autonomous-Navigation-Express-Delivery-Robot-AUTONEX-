"""
QR Command Handler

Converts a decoded, CONFIRMED QR marker payload into a navigation command.

Example:
    "MARKER 1" -> "START"
    "MARKER 2" -> "STRAIGHT"
    "MARKER 3" -> "RIGHT"
    "MARKER 4" -> "LEFT"
    "MARKER 5" -> "DESTINATION"
    "STOP"     -> "STOP"

This is intentionally a plain lookup table (config.settings.QR_COMMAND_MAP),
not an enum/dispatcher registry. Adding a new marker for a bigger campus is
one line in settings.py; nothing here changes.
"""
import logging

from config import settings

logger = logging.getLogger(__name__)


class QRCommandHandler:

    def __init__(self, command_map=None):
        self.command_map = command_map or settings.QR_COMMAND_MAP

    def parse(self, qr_data: str):
        if not qr_data:
            return None

        key = qr_data.strip().upper()

        command = self.command_map.get(key)

        if command is None:
            logger.warning("Ignoring unrecognized QR marker: %s", qr_data)
            return None

        logger.info("QR '%s' mapped to command '%s'", key, command)

        return command
