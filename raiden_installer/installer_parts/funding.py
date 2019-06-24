from raiden_contracts.contract_manager import (
    ContractManager,
    contracts_precompiled_path,
    get_contracts_deployment_info
)
from raiden_contracts.constants import (
    CONTRACT_USER_DEPOSIT,
    CONTRACT_CUSTOM_TOKEN
)


class PfsAndMonitoringFunding:
    '''
    Creates a Web3 contract object for the custom token
    contract and the user deposit contract and provides
    methods for minting tokens, approving a deposit and
    making the deposit.
    '''
    def __init__(self, w3, address, private_key):
        contract_manager = ContractManager(contracts_precompiled_path())
        user_deposit_abi = (
            contract_manager.get_contract_abi(CONTRACT_USER_DEPOSIT)
        )
        custom_token_abi = (
            contract_manager.get_contract_abi(CONTRACT_CUSTOM_TOKEN)
        )

        self.w3 = w3
        self.address = address
        self.private_key = private_key

        self.chain_id = int(self.w3.net.version)

        self.user_deposit_address = (
            get_contracts_deployment_info(
                self.chain_id
            )['contracts'][CONTRACT_USER_DEPOSIT]['address']
        )
        self.user_deposit_contract = self.w3.eth.contract(
            address=self.user_deposit_address,
            abi=user_deposit_abi
        )

        custom_token_address = (
            self.user_deposit_contract.functions.token().call()
        )
        self.custom_token_contract = self.w3.eth.contract(
            address=custom_token_address,
            abi=custom_token_abi
        )
        
    def mint_tokens(
        self,
        token_amount: int,
        gas: int,
        gas_price: int
    ) -> tuple:
        mint = self.custom_token_contract.functions.mint(
            token_amount
        ).buildTransaction(
            {
                'chainId': self.chain_id,
                'gas': gas,
                'gasPrice': gas_price,
                'nonce': w3.eth.getTransactionCount(self.address)
            }
        )
        sign_mint = self.w3.eth.account.signTransaction(
            mint,
            self.private_key
        )

        transaction_hash = self.w3.eth.sendRawTransaction(
            sign_mint.rawTransaction
        )
        transaction_receipt = self.w3.eth.waitForTransactionReceipt(
            transaction_hash
        )
        transaction_status = transaction_receipt['status']

        transaction_details = (transaction_status, transaction_hash.hex())
        return transaction_details

    def approve_deposit(
        self,
        token_amount: int,
        gas: int,
        gas_price: int
    ) -> tuple:
        approve = self.custom_token_contract.functions.approve(
            self.user_deposit_address,
            token_amount
        ).buildTransaction(
            {
                'chainId': self.chain_id,
                'gas': gas,
                'gasPrice': gas_price,
                'nonce': w3.eth.getTransactionCount(self.address)
            }
        )
        sign_approve = self.w3.eth.account.signTransaction(
            approve,
            self.private_key
        )

        transaction_hash = self.w3.eth.sendRawTransaction(
            sign_approve.rawTransaction
        )
        transaction_receipt = self.w3.eth.waitForTransactionReceipt(
            transaction_hash
        )
        transaction_status = transaction_receipt['status']

        transaction_details = (transaction_status, transaction_hash.hex())
        return transaction_details

    def make_deposit(
        self,
        token_amount: int,
        gas: int,
        gas_price: int
    ) -> tuple:
        deposit = self.user_deposit_contract.functions.deposit(
            self.address,
            token_amount
        ).buildTransaction(
            {
                'chainId': self.chain_id,
                'gas': gas,
                'gasPrice': gas_price,
                'nonce': w3.eth.getTransactionCount(self.address)
            }
        )
        sign_deposit = self.w3.eth.account.signTransaction(
            deposit,
            self.private_key
        )

        transaction_hash = self.w3.eth.sendRawTransaction(
            sign_deposit.rawTransaction
        )
        transaction_receipt = self.w3.eth.waitForTransactionReceipt(
            transaction_hash
        )
        transaction_status = transaction_receipt['status']

        transaction_details = (transaction_status, transaction_hash.hex())
        return transaction_details