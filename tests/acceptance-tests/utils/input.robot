*** Settings ***
Documentation       Utility keywords to interact with the raiden installer's
...                 interface. It abstracts away details on how input is passed on
...                 to the interactive prompt / gui.

Variables           ../variables.py


*** Keywords ***
Select
    [Documentation]     Passes the given ${OPTION} to the installer.
    ...                 Under the hood, this detects if it needs to be passed
    ...                 to an interactive prompt, or a selection needs to be
    ...                 made via a GUI.

    ...                 Should the currently running installer be run in GUI mode,
    ...                 this will fail instantly if the selection is not valid.
    ...
    ...                 ${EXPECTED_STEP} may be passed to execute a step assertion
    ...                 before passing the selection on to the interface.
    ...
    ...                 All other "SELECT" keywords build upon this keyword.

    [Arguments]         ${OPTION}   ${EXPECTED_STEP}=

# Step 1-related Keywords
# Note that these are at the moment mostly syntactic sugar.

Select STEP 1 Option
    [Documentation]     Select an ${OPTION} expected in ${STRINGS.STEP_1}.
    Select                  ${OPTION}   EXPECTED_STEP=${STRINGS.STEP_1}

Select Raiden Install Directory
    [Documentation]     Pass the ${DIR} to the installer. We expect the installer
    ...                 to be in the Raiden Binary installation step.

    [Arguments]             ${DIR}

    Select STEP 1 Option    ${DIR}

Select Raiden Version
    [Documentation]     Select the given ${VERSION} within the installer.
    ...                 We expect to be in the Raiden Binary installation step.

    [Arguments]         ${VERSION}

    Select STEP 1 Option    ${VERSION}

# Assertions
Assert input was accepted
    [Documentation]     Ensure our previous selection was accepted by the installer.

Assert input was rejected
    [Documentation]     Ensure the previous selection was rejected by the installer.
