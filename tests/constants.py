import tempfile
from pathlib import Path

TESTING_TEMP_FOLDER = Path(tempfile.gettempdir()).joinpath("raiden-wizard-testing")
TESTING_KEYSTORE_FOLDER = TESTING_TEMP_FOLDER.joinpath("keystore")
