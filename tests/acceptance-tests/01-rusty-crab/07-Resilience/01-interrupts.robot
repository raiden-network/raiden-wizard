*** Settings ***
Documentation       Test the Raiden installer's logic for handling failures and
...                 interrupts during the installation process. This includes
...                 clean up of possibly created files, and updating meta data
...                 about the installation process, in order to be able to
...                 pick up at the last successful installation step.

*** Test Cases ***
Interrupting the Raiden Client step cleans up temporary files
Interrupting the Raiden Client step causes installer to pick up at beginning of this step

Interrupting the Ethereum Client step cleans up temporary files
Interrupting the Ethereum Client step causes installer to pick up at beginning of this step

Interrupting the Account Setup step cleans up temporary files
Interrupting the Account Setup step causes installer to pick up at beginning of this step

Interrupting the Account Funding step cleans up temporary files
Interrupting the Account Funding step causes installer to pick up at beginning of this step

Interrupting the Token Acquisition step cleans up temporary files
Interrupting the Token Acquisition step causes installer to pick up at beginning of this step


*** Keywords ***

Interrupting the Raiden Client step cleans up temporary files
    Fail    "Test not Implemented!"

Interrupting the Raiden Client step causes installer to pick up at beginning of this step
    Fail    "Test not Implemented!"


Interrupting the Ethereum Client step cleans up temporary files
    Fail    "Test not Implemented!"

Interrupting the Ethereum Client step causes installer to pick up at beginning of this step
    Fail    "Test not Implemented!"


Interrupting the Account Setup step cleans up temporary files
    Fail    "Test not Implemented!"

Interrupting the Account Setup step causes installer to pick up at beginning of this step
    Fail    "Test not Implemented!"


Interrupting the Account Funding step cleans up temporary files
    Fail    "Test not Implemented!"

Interrupting the Account Funding step causes installer to pick up at beginning of this step
    Fail    "Test not Implemented!"


Interrupting the Token Acquisition step cleans up temporary files
    Fail    "Test not Implemented!"

Interrupting the Token Acquisition step causes installer to pick up at beginning of this step
    Fail    "Test not Implemented!"


