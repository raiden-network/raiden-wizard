*** Settings ***
Documentation       Test the Raiden installer's download step logic for the Raiden binary.

Variables            ../../variables.py

*** Test Cases ***
RI downloads latest version of Raiden binary
    [Documentation]     The Raiden installer downloads the latest binary from
    ...                 the github releases page and puts it in ${RAIDEN_INSTALL_PATH}/downloads.

    Fail        "Test Not Implemented!"