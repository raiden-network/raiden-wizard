*** Settings ***
Documentation       Test the Raiden installer's download step logic for the Raiden binary.

Library             OperatingSystem
Library             HTTPLibrary
Variables           ../../variables.py
Resource            ../../utils/input.robot
Resource            ../../utils/installer.robot

Test Setup          Start CLI Installer
Test Teardown       Stop Installer

*** Test Cases ***
RI downloads latest version of Raiden binary
    [Documentation]     The Raiden installer downloads the latest binary from
    ...                 the github releases page and puts it in ${RAIDEN_INSTALL_PATH}/cache.

    Select Raiden Install Directory     ${RAIDEN_INSTALL_DIR}
    Select Raiden Version               LATEST

    Directory Should Exist  ${RAIDEN_INSTALL_DIR}/cache

    ${EXPECTED_ARCHIVE}=    Get Latest Binary Archive File Name
    File Should Exist       ${RAIDEN_INSTALL_PATH}/cache/${EXPECTED_ARCHIVE}


*** Keywords ***
Get Latest Binary Archive File Name
    [Documentation]     Fetch the name of the latest raiden binary archive from our Raiden space.

    Create HTTP Context     host=${RAIDEN_SPACE}
    GET                     /_LATEST-linux-x86_64.txt
    ${ARCHIVE_FILE_NAME}=   Get Response Body

    [Return]            ${ARCHIVE_FILE_NAME}
