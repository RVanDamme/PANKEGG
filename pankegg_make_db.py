#!/usr/bin/env python
"""Compatibility wrapper so that ``python pankegg_make_db.py ...`` keeps working
from a repository checkout. The code lives in ``pankegg/make_db.py``; installed
users run the ``pankegg_make_db`` command instead.
"""

import sys

from pankegg import make_db as _impl

if __name__ == "__main__":
    sys.exit(_impl.main())
else:
    # ``import pankegg_make_db`` gives the real module, so attribute patches
    # (e.g. in tests) reach the code that runs.
    sys.modules[__name__] = _impl
