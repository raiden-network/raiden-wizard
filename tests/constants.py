import tempfile
from pathlib import Path

TESTING_TEMP_FOLDER = Path(tempfile.gettempdir()).joinpath("raiden-wizard-testing")
