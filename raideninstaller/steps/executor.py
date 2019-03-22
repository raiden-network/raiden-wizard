"""StepExecution Context manager module.

.. glossary:

    installation meta files

        A hidden folder in raiden's install directory (default location
        /opt/raiden/.meta) which holds meta data about the installation,
        such as steps executed, the last successfully executed step and the
        options chosen by the user and installed by the installer.

"""
import pathlib
import json

from abc import ABC, abstractmethod
from typing import Dict

from raideninstaller.constants import PATHS


class StepExecutor(ABC):
    """Context manager for executing installation steps.

    Takes care of the following:

        - Check if the step was run already
        - Log execution success in installation meta files
        - Revert changes on failure
        - Log execution failure in installation meta files
        - Offer alternative options if the step was already executed successfully
            ('modify' installer option)

    In order to provide the above functionality, this class needs to be
    inherited and customized for each of the installation steps.

    Usage::

        class CustomStep(StepExecutor):
            def run(self):
                print("Executing..")

        with CustomStep() as step:
            step.run()

    """

    def __init__(self, name: str, install_path: pathlib.Path = PATHS.DEFAULT_INSTALL_DIR):
        self.name = name
        self.meta_path = install_path.joinpath('.meta')
        if self.meta_path.exists():
            self.meta: Dict = json.load(self.meta_path.open('r'))
        else:
            self.meta = {}
        self.install_dir = install_path

    def __enter__(self):
        """Set up the Executor context.

        We check if this step was run before; if so, we record its logged exit
        status.

        Then, we log execution start in the installation meta files and return the
        instance.

        TODO: This is a stub.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Wrap things up after step execution.

        If execution was successful (i.e. `exc_type` is None), we do the
        following:

            - We report the step as successful in the installation meta files.
            - We return from the method with a None value

        If an exception was raised during execution, the following things happen:

            - We report the failure in the installation meta files.
            - We revert any changes we may have made during this step.
            - We return a non-zero exit status using :func:`exit`.

        TODO: This is a stub.
        """
        if exc_type:
            if not self.name in self.meta:
                self.meta[self.name] = {'run_count': 1, 'previous_run_success': False}
            else:
                meta_dict = self.meta[self.name]
                meta_dict['run_count'] += 1
                meta_dict['previous_run_success'] = False
            json.dump(self.meta, self.meta_path.open('w'), indent=4)
        pass

    @property
    def is_rerun(self) -> bool:
        """Check if this step was run before.

        Should there be no section present for this step, this defaults to False.

        Should the 'rerun' key not be present, this defaults to False as well.
        """
        return self.meta.get(self.name, {}).get('run_count', 0) > 0

    @property
    def previous_run_succeeded(self) -> bool:
        """Check if the previous instance of this step was run successfully.

        Should there be no section present for this step, this defaults to False.

        Should the 'previous_run_success' key not be present, this defaults to
        False as well.
        """
        if self.is_rerun:
            return self.meta.get(self.name, {}).get('previous_run_success', False)
        return False

    @abstractmethod
    def run(self):
        """Run the installer step."""
