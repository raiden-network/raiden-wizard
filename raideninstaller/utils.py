import pathlib

from tarfile import TarFile
from zipfile import ZipFile

from typing import List, Dict, Union, Optional, Any

import requests
import shutil

from raideninstaller.constants import STRINGS, NETWORKS


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
        if len(self.files()) != 1:
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
    default: Optional[str] = None,
    options: Optional[Union[Dict[str, str], List[str]]] = None,
) -> Any:
    """Ask the user for his input.

    If `options` is specified, we will validate the input against its contents.
    Should the validation fail we print :attr:`PATHS.INPUT_REJECTED` to the
    console and ask for input again. Otherwise, :attr:`PATHS.INPUT_ACCEPTED` is
    printed instead and the input value returned.
    """
    if options:
        render_options(options)

    while True:
        response = input(prompt)
        if options is None:
            return response or default
        elif response in options:
            return response
        print(STRINGS.INVALID_SELECTION)
        if options:
            render_options(options, short_hand=True)


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
    """Download the file at given `url` to `target_path`.

    :raises requests.HTTPError:
        if the GET request to the given `url` returns a status code >399.
    """
    with requests.get(url, stream=True) as resp, target_path.open('wb+') as release_file:
        resp.raise_for_status()
        shutil.copyfileobj(resp.raw, release_file)
    return target_path


def is_testnet(network: str) -> bool:
    """Check if the given `network` is a test network."""
    return network in NETWORKS.TESTNETS

