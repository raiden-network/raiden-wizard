*** Settings ***
Documentation   Test the installation procedure for the Raiden binary. we test
...             that the installer honors user input for the symlink path, as
...             well as optionally skipping the symlink and desktop icon creation.

Variables        ../../variables.py

*** Test Cases ***
Installer creates symlink in custom path
Installer creates symlink in default path if no custom path is given
Installer skips symlink creation if specified by the user

Installer creates desktop icon for custom binary path
Installer creates desktop icon for default binary path
Installer skips creation of desktop icon if specified by the user


*** Keywords ***
Installer creates symlink in custom path
    [Documentation]     The installer creates the symlink in ${CUSTOM_SYMLINK_PATH}
    ...                 and points it to the raiden binary at ${RAIDEN_BINARY}.

    Fail        "Test Not Implemented!"

Installer creates symlink in default path if no custom path is given
    [Documentation]     The installer creates the symlink in ${DEFAULT_SYMLINK_PATH}
    ...                 and points it to the raiden binary at ${RAIDEN_BINARY}.

    Fail        "Test Not Implemented!"


Installer Skips Symlink creation if specified by the user
    [Documentation]     The installer skips creating a symlink if specified by
    ...                 the user. No symlink is created in ${DEFAULT_SYMLINK_PATH}.

    Fail        "Test Not Implemented!"


Installer creates desktop icon for custom binary path
    [Documentation]      The installer creates desktop icon and points it at
    ...                 ${CUSTOM_BIN_PATH}/raiden.

    Fail        "Test Not Implemented!"


Installer creates desktop icon for default binary path
    [Documentation]      The installer creates desktop icon and points it at
    ...                 ${RAIDEN_BINARY}

    Fail        "Test Not Implemented!"


Installer skips creation of desktop icon if specified by the user
    [Documentation]     The installer skips creating a desktop icon if specified
    ...                 by the user.

    Fail        "Test Not Implemented!"
