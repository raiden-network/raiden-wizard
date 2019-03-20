*** Settings ***
Documentation       Utility keywords to interact with the raiden installer during
...                 testing. It abstracts away details on how input is passed on
...                 to the interactive prompt / gui.

Variables           ../variables.py


*** Keywords ***
Start ${MODE: CLI|GUI} installer
    [Documentation]     Start the installer in the given `${MODE: CLI|GUI}`.

Stop Installer
    [Documentation]     Stop the installer gracefully, if possible.

Restart Installer
    [Documentation]     Stop the installer and start it up in ${MODE}.

    [Arguments]         ${MODE}

    Stop Installer
    Start ${MODE} installer

Interrupt Installer
    [Documentation]     Send a SIGINT to the installer process.

Fast forward Installer to "${STEP}"
    [Documentation]     Auto-pilot the installer to the given ${STEP}.
    ...                 If any user input is required, defaults will
    ...                 automatically be chosen.

Assert current step is "${STEP}"
    [Documentation]     Assert that the currently executed installer step is
    ...                 equal to ${STEP}.
