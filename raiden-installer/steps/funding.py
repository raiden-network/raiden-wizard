from raiden_installer.steps.executor import StepExecutor
from raiden_installer.utils import is_testnet


class AccountFundingStep(StepExecutor):
    def __init__(self, account, network, is_new_account=False):
        super(AccountFundingStep, self).__init__('funding')
        self.account = account
        self.network = network
        self.is_new_account = is_new_account

    def request_testnet_ether(self):
        """Request ether for the given `account` from somewhere.

        TODO: This is a stub.
        """

    def fund_mainnet_account(self):
        """Magically fund your main net account out of thin air.

        ..or something.

        TODO: This is a stub.
        """

    def run(self):
        """Execute the account funding step.

        TODO This is a stub.
        """
        if is_testnet(self.network):
            self.request_testnet_ether()
        else:
            if self.is_new_account:
                self.fund_mainnet_account()
            else:
                # Do nothing - existing accounts should be funded by the user.
                pass
