import pathlib

from raiden_installer.constants import PATHS, RAIDEN_META
from raiden_installer.steps.executor import StepExecutor
from raiden_installer.utils import (
    create_symlink,
    create_desktop_icon,
    download_file,
    extract_archive,
    ReleaseArchive,
    user_input,
)


class RaidenInstallationStep(StepExecutor):

    def __init__(self, install_dir: pathlib.Path=PATHS.DEFAULT_INSTALL_DIR):
        super(RaidenInstallationStep, self).__init__('raiden', install_dir)
        self.download_dir = self.install_dir.joinpath('download')
        self.archive = None
        self.binary_dir = self.install_dir.joinpath('bin')
        self.binary = None

    def download_binary(self) -> None:
        """Download the latest Raiden client binary."""
        RAIDEN_META.update()
        self.archive = download_file(self.download_dir, RAIDEN_META.DOWNLOAD_URL)

    def install_binary(self) -> None:
        """Install the binary on this machine, unpacking the archive if necessary."""
        with ReleaseArchive(self.archive) as archive:
            self.binary = archive.unpack(self.binary_dir.join(RAIDEN_META.BINARY_NAME))

    def configure_client(self, network: str) -> None:
        """configure the client to use the given `network`.

        TODO: This is a stub.
        """

    def run(self):
        """Execute the Raiden client installation step.

        We download the binary from the download url specified in
        :attr:`RAIDEN_META.DOWNLOAD_URL` and place it in `<INSTALL DIR>/download`,
        and unpack the archive; the resulting binary is copied to
        `<INSTALL DIR>/bin`.

        Once this is done, we ask the user if a symbolic link should be created
        in :attr:`PATHS.USR_BIN_DIR`, and if so, create it.

        We repeat the procedure for a desktop icon linking to the installed binary.

        Next, we determine which network the user would like to connect to.
        Their input is used to configure the raiden client appropriately.

        Finally, we show the 'Safe Usage Requirements' to the user, and have them
        confirm that they read it.

        Once this is happens, the step is complete and we return.
        """
        # Download the binary
        self.download_binary()

        # Copy binary to the directory specified in self.install_dir.
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
