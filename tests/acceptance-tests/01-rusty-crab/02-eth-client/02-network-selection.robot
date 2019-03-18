*** Settings ***
Documentation    Test that the Raiden installer allows selecting one of the four
...              test networks on setup.
Variables            ../../variables.py

*** Test Cases ***
Selecting "${RINKEBY}" while using "${GETH}" results in "${FAILURE}"
Selecting "${RINKEBY}" while using "${PARITY}" results in "${SUCCESS}"

Selecting "${KOVAN}" while using "${GETH}" results in "${FAILURE}"
Selecting "${KOVAN}" while using "${PARITY}" results in "${SUCCESS}"

Selecting "${ROPSTEN}" while using "${GETH}" results in "${SUCCESS}"
Selecting "${ROPSTEN}" while using "${PARITY}" results in "${SUCCESS}"

Selecting "${GOERLI}" while using "${GETH}" results in "${SUCCESS}"
Selecting "${GOERLI}" while using "${PARITY}" results in "${SUCCESS}"

*** Keywords ***
Selecting "${NETWORK}" while using "${CLIENT}" results in "${OUTCOME}"
    [Documentation]    Assert whether the given combination of ${CLIENT} and
    ...                 ${NETWORK} results in the expected ${OUTCOME}.

    Fail        "Test Not Implemented!"

RI allows Selecting a specific Test Network

    [Arguments]         ${CLIENT}
    ...                 ${NETWORK}
    ...                 ${SHOULD_SUCCEED}

    Fail        "Test Not Implemented!"
