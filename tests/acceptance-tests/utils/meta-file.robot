*** Settings ***
Documentation       Keywords for interacting and asserting data and states in the
...                 installer's meta file.

Variables           ../variables.py


*** Keywords ***
Read Meta File
    [Documentation]     Read the installer meta file located at ${RAIDEN_INSTALL_DIR}/.meta.
    ...                 This returns the contents of the file as a dictionary,
    ...                 where each section name is a dict key and their content
    ...                 the key's value.

    [Arguments]         ${PATH}=${RAIDEN_INSTALL_DIR}/.meta

Clear Meta File
    [Documentation]     Remove the installer meta files located at ${RAIDEN_INSTALL_DIR}/.meta

    [Arguments]         ${PATH}=${RAIDEN_INSTALL_DIR}/.meta
