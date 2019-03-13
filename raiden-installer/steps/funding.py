from raiden_installer.steps.executor import StepExecutor
from raiden_installer.utils import is_testnet


class AccountFundingStep(StepExecutor):

    def request_testnet_ether(self, account: str, network: str):
        """Request ether for the given `account`

        TODO: This is a stub.
        """
        return account, network

    def fund_mainnet_account(self, account):
        """Magically fund your main net account out of thin air.

        ..or something.

        TODO: This is a stub.
        """
        return account

    def fund_account(self, network, account):
        if is_testnet(network):
            self.request_testnet_ether(account, network)
        else:
            if create_account:
                self.fund_mainnet_account(account)
            else:
                # Do nothing - existing accounts should be funded by the user.
                pass
