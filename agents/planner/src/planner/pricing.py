"""Re-export of the shared pricing table.

The table moved to ``platform_shared.pricing`` in card 08 (the Developer agent needs it
too, and agents must not depend on each other). This module stays so existing imports
keep working.
"""

from platform_shared.pricing import compute_cost

__all__ = ["compute_cost"]
