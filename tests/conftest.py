import zipfile
import os
from urllib.request import urlopen
import pytest

TEST_DATA_URL = "https://osf.io/download/5v3zc/"

@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """Download and extract the OSF test dataset.

    The current working directory is changed to the parent directory of the
    extracted ``pankegg_test_data`` folder so that tests relying on relative
    paths in the CSV files work as expected. The original working directory is
    restored when the tests finish.
    """

    tmp = tmp_path_factory.mktemp("pankegg_data")
    zip_path = tmp / "pankegg_test_data.zip"
    try:
        with urlopen(TEST_DATA_URL) as resp:
            zip_path.write_bytes(resp.read())
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
        data_dir = tmp / "pankegg_test_data"
        if not data_dir.exists():
            data_dir = tmp

        original_cwd = os.getcwd()
        os.chdir(data_dir.parent)
        yield data_dir
    except Exception:
        pytest.skip("pankegg test data not available")
    finally:
        if "original_cwd" in locals():
            os.chdir(original_cwd)