#!/usr/bin/env python
"""Compatibility wrapper so that ``python pankegg_app.py ...`` keeps working
from a repository checkout. The code lives in ``pankegg/app.py``; installed
users run the ``pankegg_app`` command instead.
"""

import sys

from pankegg import app as _impl

if __name__ == "__main__":
    _impl.start_server()
else:
    sys.modules[__name__] = _impl
