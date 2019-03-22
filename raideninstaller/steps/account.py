from raideninstaller.steps.executor import StepExecutor
from raideninstaller.utils import user_input


class AccountSetupStep(StepExecutor):

    def __init__(self, client):
        self.client = client
        self.account = None

    def setup_account(self):
        """Create a new account using the given client.

        TODO This is a stub.
        """
        self.account = ''

    def run(self):
        """Execute the account creation step.

        TODO This is a stub.
        """
        # Determine if we need to setup a new account for the user
        create_account = user_input(
            "Your selection: [1]",
            default=1,
            options=[
                'User existing Ethereum user account',
                'Create a new Ethereum account'
            ]
        )

        if create_account:
            self.setup_account()
        else:
            self.account = user_input("Please specify the account to use:")

