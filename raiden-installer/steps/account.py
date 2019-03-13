import pathlib

from raiden_installer.steps.executor import StepExecutor
from raiden_installer.utils import user_input


class AccountSetupStep(StepExecutor):

    def __init__(self, client):
        self.client = client

    def setup_account(self) -> Any:
        """Create a new account using the given client.

        TODO This is a stub.
        """

    def account_setup(self):
        """Execute the account creation step.

        TODO This is a stub.
        """
        # Determine if we need to setup a new account for the user
        # TODO: User input require input validation.
        print(
            "\nPlease select one:"
            "   [1] Use existing Ethereum user account"
            "   [2] Create a new Ethereum account\n",
        )
        options = ['User existing Ethereum user account', 'Create a new Ethereum account']
        create_account = user_input("Your selection: [1]"), default=1, options=options)

        if create_account:
            account = self.setup_account(self.client)
        else:
            account = user_input("Please specify the account to use:")

        return account
