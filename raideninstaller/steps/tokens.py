from raideninstaller.steps.executor import StepExecutor
from raideninstaller.utils import user_input, is_testnet


class TokenAcquisitionStep(StepExecutor):

    def __init__(self, network, account):
        self.account = account
        self.network = network

    def acquire_token(self, token: str) -> None:
        """Acquire the given `token` on the given `network`.

        TODO: This is a stub.
        """

    def token_acquisition(self):
        """Execute the token acquisition step.

        TODO: This is a stub.
        """
        if is_testnet(self.network):
            token = user_input('Specify a token to acquire:')
            self.acquire_token(token)
        else:
            # Skipping token acquisition for Main network.
            pass
