import pathlib

from tarfile import TarFile
from zipfile import ZipFile

from typing import List, Dict, Union, Optional, Any

import requests
import shutil

from raideninstaller.constants import STRINGS, NETWORKS, RAIDEN_META


class ReleaseArchive:
    """Wrapper class for extracting a Raiden release from its archive.

    Supplies a context manager and file-type detection, which allows choosing
    the correct library for opening the archive automatically.
    """
    def __init__(self, path: pathlib.Path):
        self.path = path
        if self.path.suffix == '.gz':
            self._context = TarFile.open(self.path, 'r:*')
        else:
            self._context = ZipFile(self.path, 'r')
        self.validate()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        # Only try closing our context if it exists.
        # An error may occur while trying to assign the context, hence it may
        # end up not being assigned to the instance.
        if hasattr(self, '_context'):
            self.close()

    @property
    def files(self):
        """Return a list of files present in the archive.

        Depending on the file extension, we choose the correct method to access
        this list.
        """
        if self.path.suffix == '.gz':
            return self._context.getnames()
        else:
            return self._context.namelist()

    @property
    def binary(self):
        """Return the name of the first file of our list of files.

        Since the archive must only contain a single file, this is automatically
        assumed to be our binary; this assumption *is not* checked for correctness.
        """
        return self.files[0]

    def validate(self):
        """Confirm there is only one file present in the archive."""
        if len(self.files) != 1:
            raise ValueError(
                f'Release archive has unexpected content. '
                f'Expected 1 file, found {len(self.files)}: {", ".join(self.files)}',
            )

    def unpack(self, target_dir: pathlib.Path):
        """Unpack this release's archive to the given `target_dir`.

        We also set the x bit on the extracted binary.
        """
        self._context.extract(self.binary, target_dir)
        target_dir.chmod(0o770)
        return target_dir

    def close(self):
        """Close the context, if possible."""
        if self._context and hasattr(self._context, 'close'):
            self._context.close()


def render_options(
    options: Union[List[str], Dict[str, str]],
    short_hand: bool=False,
) -> None:
    """Render the given options to the console.

    If `short_hand` is True, we render a shorter description of options. Output
    depends on the type of `options`.

    If `options` is a list, we display it as a numbered list of its element::

        >>>ops = ['potato', 'tomato', 'sangria']
        ['potato', 'tomato', 'sangria']
        >>>render_options(ops)
        "Choose one of the following:"
        "    [1]    potato"
        "    [2]    tomato"
        "    [3]    sangria"

    Or, if a short hand is requested, we condense it to a single line:

        >>>render_options(ops, short_hand=True)
        "Choose one of [1, 2, 3]:"

    Should `options` be a dictionary, we use the keys instead::

        >>>ops = {'ok': 'potato', 'better': 'tomato', 'best': 'sangria'}
        ['potato', 'tomato', 'sangria']
        >>>render_options(ops)
        "Choose one of the following:"
        "    [ok]       potato"
        "    [better]   tomato"
        "    [best]     sangria"
        >>>render_options(ops, short_hand=True)
        "Choose one of [ok, better, best]:"

    TODO: This is a stub
    """
    choose_long = 'Choose one of the following:\n'
    if short_hand:
        return print(f'Choose one of {[x for x in options]}')

    if isinstance(options, list):
        label_description_list = enumerate(options)
    else:
        label_description_list = list((options).items())

    for label, descr in label_description_list:
        choose_long += f'    [{label}]    {descr}\n'

    return print(choose_long)


def user_input(
    prompt: str,
    default: Optional[Union[str, int, float]] = None,
    options: Optional[Union[Dict[str, str], List[str]]] = None,
    short_hand: bool = False,
) -> Any:
    """Ask the user for his input.

    If `options` is specified, we will validate the input against its contents.
    Should the validation fail we print :attr:`PATHS.INPUT_REJECTED` to the
    console and ask for input again. Otherwise, :attr:`PATHS.INPUT_ACCEPTED` is
    printed instead and the input value returned.
    """
    acceptable_input = None
    if options:
        render_options(options, short_hand)
        acceptable_input = [str(x) for x in range(len(options))] if isinstance(options, list) else options.keys()

    while True:
        response = input(prompt)
        if options is None or (not response and default):
            print(STRINGS.SELECTION_ACCEPTED)
            return response or default
        elif not response and not default:
            print(STRINGS.SELECTION_CANNOT_BE_EMPTY)
        elif response in acceptable_input:
            print(STRINGS.SELECTION_ACCEPTED)
            return options[response]
        else:
            print(STRINGS.SELECTION_REJECTED)
        if options:
            render_options(options, short_hand=True)


def yes_no_input(prompt, default='yes') -> bool:
    """Wrapper for asking y/n input from the user.

    Answer is returned as a bool.
    """
    assert default in ('yes', 'no')
    reply = user_input(prompt, default=default, options=['yes', 'no'], short_hand=True)
    if reply == 'yes':
        return True
    return False


def create_symlink(bin_path: pathlib.Path, symlink_name: str, flags: Optional[List[str]]=None) -> None:
    """Create a symlink at /usr/local/bin for the given `bin_path`.

    If `flags` is truthy, we create a script at /usr/local/bin instead, which
    executes the target using bash and the given flags.
    """
    if flags:
        with open(f'/usr/local/bin/{symlink_name}', 'w+') as f:
            f.write('#!/usr/bin/bash\n')
            f.write(f'{bin_path} {" ".join(flags)}')
    else:
        pathlib.Path(f'/usr/local/bin/{symlink_name}').symlink_to(bin_path)


def create_desktop_icon(target: pathlib.Path, symlink_name: str) -> None:
    """Create a desktop icon for the given `target`."""
    return pathlib.Path.home().joinpath(symlink_name).symlink_to(target)


def download_file(target_path: pathlib.Path, url: str) -> pathlib.Path:
    """Download this release's binary from our servers to the given `target_path`."""

    with requests.get(url, stream=True) as resp:
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise ValueError(
                f"Can't download file from {url}!",
            ) from e
        with target_path.open('wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)

    return target_path


def is_testnet(network: str) -> bool:
    """Check if the given `network` is a test network."""
    return network in NETWORKS.TESTNETS

