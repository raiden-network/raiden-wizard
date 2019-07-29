#!/bin/bash

# Assuming the virtualenv is already activated

PWD=$(dirname "$0")
PROJECT_ROOT="$PWD/.."
DIST_FOLDER="$PROJECT_ROOT/dist"
BINARY_NAME="raiden_wizard"

if [ -z "$VIRTUAL_ENV" ]; then
    printf "Virtualenv environment needs to be set"
    exit;
fi

pip install -r "$PROJECT_ROOT/requirements.txt" -I

pip install pyinstaller staticx patchelf-wrapper
pyinstaller "$PWD/pyinstaller/raiden_webapp.spec"

if [ "$OSTYPE" == "linux-gnu" ]; then
    staticx "$DIST_FOLDER/$BINARY_NAME" "${PROJECT_ROOT}/${BINARY_NAME}.${OSTYPE}.bin"
fi
