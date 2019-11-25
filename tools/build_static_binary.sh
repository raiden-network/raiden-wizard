#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Usage: build_static_binary.sh path/to/configuration.toml"
    exit -1
fi

PWD=$(dirname "$0")

# realpath is not always available on macOS, so we resort to get the path via python
SETTINGS_SOURCE_FILE=`python -c "import os; print(os.path.abspath('$1'))"`

PROJECT_ROOT="$PWD/.."
DIST_FOLDER="$PROJECT_ROOT/dist"
BINARY_NAME="raiden_wizard"
SETTINGS_FILE="$PROJECT_ROOT/resources/conf/settings.toml"

# Virtualenv must be activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: python virtualenv needs to be activated"
    exit -2
fi

rm $SETTINGS_FILE
cp $SETTINGS_SOURCE_FILE $SETTINGS_FILE

pip install -r "$PROJECT_ROOT/requirements.txt" -I

pip install pyinstaller staticx patchelf-wrapper
pyinstaller "$PWD/pyinstaller/raiden_webapp.spec"

if [ "$OSTYPE" == "linux-gnu" ]; then
    staticx "$DIST_FOLDER/$BINARY_NAME" "${PROJECT_ROOT}/${BINARY_NAME}.${OSTYPE}.bin"
fi
