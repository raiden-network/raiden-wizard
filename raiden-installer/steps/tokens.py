from raiden_installer.steps.executor import StepExecutor
from raiden_installer.utils import user_input


class TokenAcquisitionStep(StepExecutor):

    def acquire_token(self, network: str, token: str) -> None:
        """Acquire the given `token` on the given `network`.

        TODO: This is a stub.
        """

    def token_acquisition(self, network, is_testnet):
        """Execute the token acquisition step.

        TODO: This is a stub.
        """
        if is_testnet(network):
            # TODO: User input require input validation.
            token = user_input('Specify a token to acquire:')
            self.acquire_token(token)
        else:
            # Skipping token acquisition for Main network.
            pass
