import pathlib

from raiden_installer.constants import PATHS
from raiden_installer.steps.executor import StepExecutor
from raiden_installer.utils import (
    create_symlink,
    create_desktop_icon,
    download_file,
    extract_archive,
    user_input,
)


class RaidenInstallationStep(StepExecutor):

    def __init__(self, install_dir: pathlib.Path=PATHS.DEFAULT_INSTALL_DIR):
        super(RaidenInstallationStep, self).__init__('raiden', install_dir)
        self.download_dir = self.install_dir.joinpath('download')
        self.archive = None
        self.binary_dir = self.install_dir.joinpath('bin')
        self.binary = None

    def download_binary(self):
        """Download the latest Raiden client binary.

        TODO: This is a stub.
        """
        self.archive = download_file(self.download_dir, self.raiden_version)

    def install_binary(self):
        """Install the binary on this machine, unpacking the archive if necessary.

        TODO: This is a stub.
        """
        self.binary = extract_archive(self.archive, self.binary_dir)

    def configure_client(self, network: str) -> None:
        """configure the client to use the given `network`.

        TODO: This is a stub.
        """

    def show_safe_usage_requirements(self) -> None:
        """Print safe usage requirements to console.

        TODO: This is a stub.
        """
        print("Always wear a helmet when hacking on raiden!")

    def run(self):
        # Download the binary
        self.download_binary()

        # Copy binary to given directory.
        self.install_binary()

        # Determine whether or not we should create a symbolic link and desktop icon
        # for the raiden client.
        symbolic_link = user_input("Add a symbolic link to /usr/local/bin for Raiden? [Y/n]", default='yes', options=['yes', 'no'])
        if symbolic_link == 'yes':
            create_symlink(self.binary)

        desktop_icon = user_input('Would you like to create a desktop icon for the Raiden client?')
        if desktop_icon:
            create_desktop_icon(self.binary)

        # Configure the client
        network = user_input("Your selection: [1]", default=1, options=['Test Network', 'Main Network'])
        self.configure_client(network)

        # Display the requirements for safe usage and have the user confirm he read them.
        self.show_safe_usage_requirements()
