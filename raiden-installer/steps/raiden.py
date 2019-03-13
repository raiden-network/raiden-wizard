import pathlib

from raiden_installer.steps.executor import StepExecutor
from raiden_installer.utils import (
    create_symlink,
    create_desktop_icon,
    download_file,
    extract_archive,
    user_input,
)


class RaidenInstallationStep(StepExecutor):

    def download_raiden_binary(self, target_path: pathlib.Path) -> pathlib.Path:
        """Download the latest Raiden client binary.

        TODO: This is a stub.
        """
        path = download_file(target_path, "version_string")
        return path

    def install_raiden_binary(
            self,
            archive_path: pathlib.Path,
            target_path: pathlib.Path
    ) -> pathlib.Path:
        """Install the Raiden binary on this machine, unpacking the archive if necessary.

        TODO: This is a stub.
        """
        return target_path

    def configure_raiden_client(self, bin_path: pathlib.Path, network: str) -> None:
        """configure the raiden client to use the given `network`.

        TODO: This is a stub.
        """

    def show_safe_usage_requirements(self) -> None:
        """Print safe usage requirements to console.

        TODO: This is a stub.
        """
        print("Always wear a helmet when hacking on raiden!")

    def install_raiden(self, download_cache_dir, binary_dir):
        # Download the binary
        archive_dir = self.download_raiden_binary(download_cache_dir)

        # Extract the archive
        bin_path = extract_archive(archive_dir, binary_dir)

        # Copy binary to given directory.
        self.install_raiden_binary(bin_path)

        # Determine whether or not we should create a symbolic link and desktop icon
        # for the raiden client.

        symbolic_link = user_input("Add a symbolic link to /usr/local/bin for Raiden? [Y/n]", default='yes', options=['yes', 'no'])
        if symbolic_link == 'yes':
            create_symlink(bin_path)

        desktop_icon = user_input('Would you like to create a desktop icon for the Raiden client?')
        if desktop_icon:
            create_desktop_icon(bin_path)

        # Configure Raiden
        network = user_input("Your selection: [1]", default=1, options=['Test Network', 'Main Network'])
        self.configure_raiden_client(bin_path, network)

        # Display the requirements for safe usage and have the user confirm he read them.
        self.show_safe_usage_requirements()
