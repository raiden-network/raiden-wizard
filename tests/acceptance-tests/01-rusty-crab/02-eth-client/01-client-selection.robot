*** Settings ***
Documentation       Test the Raiden installer's client selection logic.

Variables            ../../variables.py


*** Test Cases ***
Installer lets the user connect to a network using an Infura Node

Installer Asserts Sync State of local synced Parity client correctly
Installer Asserts Sync State of local unsynced Parity client correctly
Installer Asserts Sync State of local synced GETH client correctly
Installer Asserts Sync State of local unsynced GETH client correctly

Installer Asserts Sync State of remote synced Parity client correctly
Installer Asserts Sync State of remote unsynced Parity client correctly
Installer Asserts Sync State of remote synced GETH client correctly
Installer Asserts Sync State of remote unsynced GETH client correctly

*** Keywords ***
Installer lets the user connect to a network using an Infura Node
    [Documentation]     The installer allows connecting to the network using an Infura Node.
    ...                 Upon specification of this connection method, a project ID is requested and validated.

    # Expected Success
    RI offers connecting to network via Infura Node     ${VALID_INFURA_ID}
    # Expected failure
    RI offers connecting to network via Infura Node     ${INVALID_INFURA_ID}


Installer allows selecting local Geth client
    RI allows using client to connect to network    ${GETH}            ${LOCAL_CLIENT_PATH}

Installer allows selecting remote Geth client
    RI allows using client to connect to network    ${GETH}            ${REMOTE_CLIENT_PATH}

Installer allows selecting local Parity client
    RI allows using client to connect to network    ${PARITY}          ${LOCAL_CLIENT_PATH}

Installer allows selecting remote Parity client
    RI allows using client to connect to network    ${PARITY}          ${REMOTE_CLIENT_PATH}


Installer Asserts Sync State of local synced Parity client correctly
    RI checks sync state of client  ${PARITY}   ${LOCAL_CLIENT_PATH}/${PARITY}  ${True}

Installer Asserts Sync State of local unsynced Parity client correctly
    RI checks sync state of client  ${PARITY}   ${LOCAL_CLIENT_PATH}/${PARITY}  ${False}

Installer Asserts Sync State of local synced GETH client correctly
    RI checks sync state of client  ${GETH}   ${LOCAL_CLIENT_PATH}/${GETH}  ${True}

Installer Asserts Sync State of local unsynced GETH client correctly
    RI checks sync state of client  ${GETH}   ${LOCAL_CLIENT_PATH}/${GETH}  ${False}

Installer Asserts Sync State of remote synced Parity client correctly
    RI checks sync state of client  ${PARITY}   ${REMOTE_CLIENT_PATH}/${PARITY}  ${True}

Installer Asserts Sync State of remote unsynced Parity client correctly
    RI checks sync state of client  ${PARITY}   ${REMOTE_CLIENT_PATH}/${PARITY}  ${False}

Installer Asserts Sync State of remote synced GETH client correctly
    RI checks sync state of client  ${GETH}   ${REMOTE_CLIENT_PATH}/${GETH}  ${True}

Installer Asserts Sync State of remote unsynced GETH client correctly
    RI checks sync state of client  ${GETH}   ${REMOTE_CLIENT_PATH}/${GETH}  ${False}

# Generic Test Keywords, which can be parametrized.
RI offers connecting to network via Infura Node
    [Documentation]     Check that the installer offers using an Infure Node to
    ...                 connect to a network. Upon selecting to connect to an
    ...                 infura node, the installer asks for a Infura project Id
    ...                 and validates it. If the validation fails, it requests
    ...                 a valid Id from the user.

    [Arguments]         ${INFURA_ID}

    Fail        "Test Not Implemented!"


RI allows using client to connect to network
    [Documentation]     The installer allows selecting the given ${CLIENT} at the givne ${LOCATION}.
    ...                 If ${LOCATION} starts with 'http', we expect the installer
    ...                 to update the symlink to the raiden binary (which must exist) with an
    ...                 adequate CLI flag to connect to the remote client.

    [Arguments]         ${CLIENT}
    ...                 ${LOCATION}

    Fail        "Test Not Implemented!"


RI checks sync state of client
    [Documentation]     The installer checks the synchronization state of the specified ${CLIENT}.
    ...                 If ${LOCATION} starts with 'http', we check that the connection
    ...                 can be established first. ${SYNCED} indicates the client state.
    ...                 If it is `False`, the expected behaviour is that the installer fails.

    [Arguments]         ${CLIENT}
    ...                 ${LOCATION}
    ...                 ${SYNCED}

    Fail        "Test Not Implemented!"
