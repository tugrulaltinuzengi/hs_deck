"""Vendored subset of HearthSim's python-hearthstone.

See ../README.md for provenance and the list of local modifications.
"""

# LOCAL MODIFICATION: upstream reads this from the installed distribution's
# metadata, which does not exist for a vendored copy.  Pinned to the version
# this tree was taken from; update it together with the sources.
__version__ = "9.21.0"
