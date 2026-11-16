"""PANKEGG: build and explore databases of metagenome-assembled genome annotations.

``pankegg_make_db`` (module :mod:`pankegg.make_db`) builds the SQLite database
using only the Python standard library. ``pankegg_app`` (module
:mod:`pankegg.app`, full ``pankegg`` distribution only) serves the web interface.
"""

__version__ = "2.1.0"

from importlib.resources import files as _files


def resource_path(*parts):
    """Absolute path of a file shipped inside the package, e.g. ``resource_path("data", "ko.txt")``."""
    return str(_files(__name__).joinpath(*parts))
