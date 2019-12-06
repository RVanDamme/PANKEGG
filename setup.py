#!/usr/bin/env python3

import sys
import platform

# Automatically download setuptools if not available
try:
    from setuptools import *
except ImportError:
    from distribute_setup import use_setuptools
    use_setuptools()
finally:
    from setuptools import *

from glob import glob

if sys.version_info == (3,8):
    print >> sys.stderr, "ERROR: NEED PYTHON 3.8"
    sys.exit()

version = open('PANKEGG/modules/version.py').read().split("=")[1]


def main():
    setup(name='PANKEGG',
          version=version,
          description="""This script is part of the MAFIN pipeline and parse the annotations files from eggnog
          as well as the quantification of the RNA reads mapped to the transcript to output
          nice html result files""",
          url='https://github.com/RVanDamme/PANKEGG',
          author='Renaud Van Damme',
          author_email='renaud.van.damme@slu.se',
          license='GNU 3.0',
          scripts=glob('PANKEGG/parser.py'),
          )


if __name__ == "__main__":
    main()