"""StepExecution Context manager module.

.. glossary:

    install cache

        A hidden folder in raiden's install directory (default location
        /opt/raiden/.install-cache) which holds meta data about the installation,
        such as steps executed, the last successfully executed step and the
        options chosen by the user and installed by the installer.

"""
from abc import ABC, abstractmethod


class StepExecutor(metaclass=ABC):
    """Context manager for executing installation steps.

    Takes care of the following:

        - Check if the step was run already
        - Log execution success in install cache
        - Revert changes on failure
        - Log execution failure in install cache
        - Offer alternative options if the step was already executed successfully
            ('modify' installer option)

    In order to provide the above functionalities, this class needs to be
    inherited and customized for each of the installation steps. However, the
    general logic and tasks is described in this class' magic methods.

    Usage::

        class CustomStep(StepExecutor):
            def run(self):
                print("Executing..")

        with CustomStep() as step:
            step.run()

    """

    def __init__(self):
        pass

    def __enter__(self):
        """Set up the Executor context.

        We check if this step was run before; if so, we record its logged exit
        status.

        Then, we log execution start in the install cache and return the
        instance.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Wrap things up after step execution.

        If execution was successful (i.e. `exc_type` is None), we do the
        following:

            - We report the step as successful in the install cache.
            - We return from the method with a None value

        If an exception was raised during execution, the following things happen:

            - We report the failure in the install cache.
            - We revert any changes we may have made during this step.
            - We return a non-zero exit status using :func:`exit`.
        """
        pass

    @abstractmethod
    def run(self):
        """Run the installer step."""
