"""One-click installer application."""
import pathlib

from raiden_installer.steps import (
    RaidenInstallationStep,
    EthClientInstallationStep,
    AccountSetupStep,
    AccountFundingStep,
    TokenAcquisitionStep,
)

from raiden_installer.utils import user_input

# Choose a default installation directory
tar_dir = user_input(
    "Choose a installation directory: [/opt/raiden]",
    default="/opt/raiden"
)
install_root_path = pathlib.Path(tar_dir)

# Create directories for installing.
install_root_path.mkdir(exist_ok=True, parents=True)
download_cache_dir = install_root_path.joinpath('cache')
binary_dir = install_root_path.joinpath('bin')

################################################################################
# Install the Raiden Client
################################################################################

with RaidenInstallationStep() as step:
    step.run()

################################################################################
# Install Ethereum Client
################################################################################

with EthClientInstallationStep() as step:
    step.run()

################################################################################
# Setup Account for Raiden Development
################################################################################

with AccountSetupStep('client') as step:
    step.run()

################################################################################
# Fund accounts with Ether
################################################################################

with AccountFundingStep() as step:
    step.run()

################################################################################
# Acquire Tokens
################################################################################

with TokenAcquisitionStep() as step:
    step.run()
