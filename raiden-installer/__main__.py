"""One-click installer application."""
import pathlib

from raiden_installer.steps import (
    RaidenInstallationStep,
    EthClientInstallationStep,
    AccountSetupStep,
    AccountFundingStep,
    TokenAcquisitionStep,
)

from raiden_installer.utils import user_input, STRINGS, PATHS

# Choose a default installation directory
tar_dir = user_input(
    f"Choose a installation directory: [{PATHS.DEFAULT_INSTALL_DIR}]",
    default=PATHS.DEFAULT_INSTALL_DIR,
)
install_root_path = pathlib.Path(tar_dir)

# Create directories for installing.
install_root_path.mkdir(exist_ok=True, parents=True)
download_cache_dir = install_root_path.joinpath('cache')
binary_dir = install_root_path.joinpath('bin')

################################################################################
# Install the Raiden Client
################################################################################

print(f'{STRINGS.STEP_1}\n')
with RaidenInstallationStep() as step:
    step.run()

################################################################################
# Install Ethereum Client
################################################################################

print(f'{STRINGS.STEP_2}\n')
with EthClientInstallationStep() as step:
    step.run()

################################################################################
# Setup Account for Raiden Development
################################################################################

print(f'{STRINGS.STEP_3}\n')
with AccountSetupStep('client') as step:
    step.run()

################################################################################
# Fund accounts with Ether
################################################################################

print(f'{STRINGS.STEP_4}\n')
with AccountFundingStep() as step:
    step.run()

################################################################################
# Acquire Tokens
################################################################################

print(f'{STRINGS.STEP_5}\n')
with TokenAcquisitionStep() as step:
    step.run()
