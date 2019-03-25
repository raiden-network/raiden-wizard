import pathlib

from raideninstaller.constants import PATHS, GETH_META
from raideninstaller.steps.executor import StepExecutor
from raideninstaller.utils import (
    create_symlink,
    create_desktop_icon,
    download_file,
    user_input
)


class EthClientInstallationStep(StepExecutor):

    def __init__(self, install_dir: pathlib.Path = PATHS.DEFAULT_INSTALL_DIR):
        super(EthClientInstallationStep, self).__init__('eth_client', install_dir)
        self.download_dir = self.install_dir.joinpath('download')
        self.archive = None
        self.binary_dir = self.install_dir.joinpath('bin')
        self.binary = None

    def download_binary(self):
        """Download the latest Ethereum client binary.

        TODO: This is a stub.
        """
        self.archive = download_file(self.download_dir, self.client_version)

    def install_binary(self):
        """Install the binary on this machine, unpacking the archive if necessary.

        TODO: This is a stub.
        """
        self.binary = extract_archive(self.archive, self.binary_dir)

    def configure_client(self, method: str) -> None:
        """configure the client to use the given `method`.

        TODO: This is a stub.
        """

    def install_private_chain() -> None:
        """Install a private chain and connect to it.

        TODO: This is a stub (and will probably remain one for quite a while).
        """

    def run(self) -> None :
        """Execute the Ethereum Client installation step.

        TODO: This is a stub.
        """
        if self.meta['raiden']['use_remote']:
            print('Using a remote client - skipping download and installation of local ethereum client.')
            return

        eth_client = user_input(
            "Use local eth client? [Yes/no]",
            default='yes',
            options=['yes', 'no']
        )
        if eth_client == 'no':
            self.download_binary()
            self.install_binary()
            make_symlink = user_input(
                "Create a symbolic link at /usr/local/bin for the Ethereum client? [Yes/no]",
                default='yes',
                options=['yes', 'no'],
                short_hand=True
            )
            if make_symlink == 'yes':
                create_symlink(self.binary, 'Ethereum Client')

            desktop_icon = user_input(
                'Would you like to create a desktop icon for the Ethereum client?',
                default='yes',
                options=['yes', 'no'],
                short_hand=True
            )
            if desktop_icon == 'yes':
                create_desktop_icon(self.binary, 'Ethereum Client')
        else:
            self.binary = user_input(
                'Please specify the path to the eth client: [/usr/local/bin/geth]',
                default=GETH_META.BIN_PATH,
                short_hand=True
            )
        # Determine which connection method we should use.
        connection_method = user_input(
            "Your selection: [1]",
            default=1,
            options=[
                'Connect to Infura',
                'Connect to an existing Ethereum Client',
                'Connect to an existing Raiden Client (launches WebUI after installation)',
                'Use local Ethereum Client and synchronize network',
                'Install a private chain'
            ]
        )

        if connection_method == 5:
            self.install_private_chain()
        else:
            self.configure_client(connection_method)
