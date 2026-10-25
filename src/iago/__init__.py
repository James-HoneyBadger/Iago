"""Iago Deluxe — a deluxe Reversi (Othello) game.

The public surface is intentionally small; import from the sub-packages::

    from iago.core import Board
    from iago.ai import Engine
"""

from .branding import VERSION as __version__

__all__ = ["__version__"]
