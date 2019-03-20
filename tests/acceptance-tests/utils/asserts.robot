*** Settings ***
Documentation       Useful assertions for usage within our acceptance tests.

Variables           ../variables.py


*** Keywords ***
Assert "${LINK}" points to "${PATH}"
    [Documentation]     Assert ${LINK} exists and points to the given ${PATH}.
    ...                 ${LINK} can either be a symlink or a desktop icon.
