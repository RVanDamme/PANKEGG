"""Test configuration.

The default test run is offline: it uses the small fixtures in tests/fixtures.
Tests that need the published OSF example archive (network) are marked
``osf`` and run only with ``pytest --run-osf``.
"""

import os
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:  # import the checkout's pankegg, not an installed one
    sys.path.insert(0, str(REPO))

TEST_DATA_URL = "https://osf.io/download/5v3zc/"


def pytest_addoption(parser):
    parser.addoption("--run-osf", action="store_true", default=False,
                     help="also run tests that download the OSF example data (network)")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "osf: needs the OSF example archive (network); run with --run-osf")
    config.addinivalue_line(
        "markers", "install: builds wheels and installs them in fresh virtual environments (slow)")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "test_data_dir" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.osf)
    if config.getoption("--run-osf"):
        return
    skip = pytest.mark.skip(reason="needs the OSF example data; run with --run-osf")
    for item in items:
        if "osf" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def osf_archive(tmp_path_factory):
    """Download and extract the OSF example archive once per session."""
    tmp = tmp_path_factory.mktemp("pankegg_data")
    zip_path = tmp / "pankegg_test_data.zip"
    try:
        with urlopen(TEST_DATA_URL, timeout=120) as resp:
            zip_path.write_bytes(resp.read())
    except OSError as e:
        pytest.fail(f"--run-osf given but the OSF example data could not be downloaded: {e}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp)
    data_dir = tmp / "pankegg_test_data"
    return data_dir if data_dir.exists() else tmp


@pytest.fixture
def test_data_dir(osf_archive, monkeypatch):
    """The extracted ``pankegg_test_data`` folder.

    The working directory is set to its parent for the duration of one test,
    because the example CSVs use paths relative to it.
    """
    monkeypatch.chdir(osf_archive.parent)
    return osf_archive
