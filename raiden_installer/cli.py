import os
import time

from whaaaaat import ValidationError, Validator, prompt

from raiden_contracts.constants import CONTRACT_USER_DEPOSIT
from raiden_installer.account import Account
from raiden_installer.base import RaidenConfigurationFile
from raiden_installer.ethereum_rpc import EthereumRPCProvider, Infura, make_web3_provider
from raiden_installer.raiden import RaidenClient
from raiden_installer.network import FundingError, Network
from raiden_installer.token_exchange import Exchange
from raiden_installer.tokens import Erc20Token, Wei, TokenAmount
from raiden_installer.utils import get_contract_address

ETHEREUM_RPC_ENDPOINTS = []
DEFAULT_INFURA_PROJECT_ID = os.getenv("RAIDEN_INSTALLER_INFURA_PROJECT_ID")

DEFAULT_NETWORK = Network.get_default()

RELEASE_MAP = RaidenClient.get_all_releases()


if DEFAULT_INFURA_PROJECT_ID:
    ETHEREUM_RPC_ENDPOINTS.append(Infura.make(DEFAULT_NETWORK, DEFAULT_INFURA_PROJECT_ID))


class Messages:
    action_launch_raiden = "Launch raiden"
    action_account_create = "Create new ethereum account"
    action_account_list = "List existing ethereum accounts"
    action_account_fund = "Add funds to account"
    action_configuration_setup = "Create new raiden setup"
    action_configuration_list = "List existing raiden setups"
    action_release_manager = "Install/Uninstall raiden releases"
    action_release_list_installed = "List installed raiden releases"
    action_release_update_info = "Check for updates in raiden"
    action_swap_kyber = "Do ETH/RDN swap on Kyber DEX (mainnet/some testnets)"
    action_quit = "Quit this raiden launcher"
    action_test = "Run semi-automated test"
    input_account_select = "Please select account"
    input_network_select = "Which ethereum network to use?"
    input_ethereum_rpc_endpoint_selection = "Which RPC node to use?"

    input_account_verify_passphrase = "Please provide the passphrase"

    input_launch_configuration = "Select setup to launch raiden"
    input_launch_release = "Select raiden version to be run"
    input_release_manager = "Check/Uncheck all releases you want to install/uninstall"
    input_passphrase = "Please provide a passphrase:"
    input_use_infura = "Use infura.io for ethereum chain operations?"
    input_ethereum_infura_project_id = "Please provide your Infura Project Id:"
    input_ethereum_rpc_endpoint = "Please provide the URL of your ethereum client RPC:"


# FIXME: Some issues with the whaaaaat library and the `validate` property of
# the `question` method not working as described and causing different types of
# errors.

# Digging a little bit on the documentation and you can find these Validator
# classes should be used by raising a ValidationError. To overcome these
# issues, the current method employed consists of
# - implementing the validator class
# - adding the validator class as `validator` to the question dict
# - Using the function `validate_prompt` instead of simple `prompt`
class InfuraProjectIdValidator(Validator):
    def validate(self):
        error_message = "A Infura Project ID is a sequence of 32 hex characters long"
        if not Infura.is_valid_project_id(self.text):
            raise ValidationError(error_message)


def validate_prompt(questions, error_message=None):
    is_validated = False
    while not is_validated:
        try:
            answers = prompt(questions)
            is_validated = True
        except (ValidationError, TypeError):
            msg = error_message or "Error validating provided information, try again."
            print(msg)
    return answers


def single_question_prompt(question_data: dict):
    key = "single_question"
    question_data["name"] = key

    return prompt(question_data).get(key)


def prompt_account_selection(validate_passphrase=True):

    account = single_question_prompt(
        {
            "type": "list",
            "message": Messages.input_account_select,
            "choices": [
                {"name": account.address, "value": account}
                for account in Account.get_user_accounts()
            ],
        }
    )

    if validate_passphrase:
        validated = False

        while not validated:
            try:
                account.unlock(
                    single_question_prompt(
                        {
                            "name": "passphrase",
                            "type": "password",
                            "message": Messages.input_account_verify_passphrase,
                        }
                    )
                )
                validated = True
            except ValueError:
                pass

    return account


def prompt_network_selection(network_list=None):
    networks = network_list or Network.all()
    return single_question_prompt(
        {
            "name": "network",
            "type": "list",
            "message": Messages.input_network_select,
            "choices": [
                {"name": network.capitalized_name, "value": network} for network in networks
            ],
            "default": DEFAULT_NETWORK if DEFAULT_NETWORK in networks else None,
        }
    )


def prompt_new_ethereum_rpc_endpoint(network=None):
    global ETHEREUM_RPC_ENDPOINTS

    if network is None:
        network = prompt_network_selection()

    ethereum_rpc_questions = [
        {
            "name": "will_use_infura",
            "type": "confirm",
            "default": True,
            "message": Messages.input_use_infura,
        },
        {
            "name": "infura_project_id",
            "type": "input",
            "message": Messages.input_ethereum_infura_project_id,
            "when": lambda answers: answers["will_use_infura"],
            "filter": lambda answer: answer.strip(),
            "validator": InfuraProjectIdValidator,
        },
        {
            "name": "ethereum_rpc_endpoint",
            "type": "input",
            "message": Messages.input_ethereum_rpc_endpoint,
            "when": lambda answers: not answers["will_use_infura"],
        },
    ]

    ethereum_rpc_answers = validate_prompt(ethereum_rpc_questions)

    if ethereum_rpc_answers["will_use_infura"]:
        project_id = ethereum_rpc_answers["infura_project_id"]
        client_rpc_endpoint = Infura.make(network, project_id)
    else:
        client_rpc_endpoint = EthereumRPCProvider(ethereum_rpc_answers["ethereum_rpc_endpoint"])

    ETHEREUM_RPC_ENDPOINTS.append(client_rpc_endpoint)

    return client_rpc_endpoint


def prompt_ethereum_rpc_endpoint_selection(network=None):
    choices = [{"name": endpoint.url, "value": endpoint} for endpoint in ETHEREUM_RPC_ENDPOINTS]

    choices.append({"name": "None of the above. Let me add another", "value": None})

    if not ETHEREUM_RPC_ENDPOINTS:
        return prompt_new_ethereum_rpc_endpoint(network=network)

    eth_rpc_endpoint = single_question_prompt(
        {
            "name": "ethereum_rpc_endpoint",
            "type": "list",
            "message": Messages.input_ethereum_rpc_endpoint_selection,
            "choices": choices,
        }
    )

    return eth_rpc_endpoint or prompt_new_ethereum_rpc_endpoint(network=network)


def print_invalid_option():
    print("Invalid option. Try again")


def pretty_print_configuration(config_file: RaidenConfigurationFile):
    account_description = (
        f"Account {config_file.account.address} (Balance: {config_file.ethereum_balance})"
    )
    network_description = (
        f"{config_file.network.name} via {config_file.ethereum_client_rpc_endpoint}"
    )
    return " - ".join((str(config_file.path), account_description, network_description))


def main_prompt():

    configuration_choices = [Messages.action_configuration_setup]
    account_choices = [Messages.action_account_create]
    raiden_release_management_choices = [Messages.action_release_manager]

    if RaidenConfigurationFile.get_available_configurations():
        configuration_choices.insert(0, Messages.action_launch_raiden)
        configuration_choices.append(Messages.action_configuration_list)

    if Account.get_user_accounts():
        account_choices.append(Messages.action_account_list)
        account_choices.append(Messages.action_account_fund)
        account_choices.append(Messages.action_swap_kyber)

    available_choices = configuration_choices + account_choices + raiden_release_management_choices

    available_choices.append(Messages.action_quit)

    return {"type": "list", "message": "What would you like to do?", "choices": available_choices}


def run_action_configuration_list():
    print("\nAvailable setups (Not necessarily satisfying conditions for running raiden)\n")
    for config in RaidenConfigurationFile.get_available_configurations():
        print("\t", pretty_print_configuration(config))

    print("\n")
    return main_prompt()


def run_action_release_manager():

    release_selection = prompt(
        {
            "name": "releases",
            "type": "checkbox",
            "message": Messages.input_release_manager,
            "choices": [
                {"name": raiden.version, "value": raiden, "checked": raiden.is_installed}
                for raiden in RELEASE_MAP.values()
            ],
        }
    )

    to_install = [release for release in release_selection["releases"]]

    for raiden in RELEASE_MAP.values():
        if raiden.is_installed and raiden.version not in to_install:
            print(f"Uninstalling {raiden.version}")
            raiden.uninstall()
            continue

        if not raiden.is_installed and raiden.version in to_install:
            print(f"Installing {raiden.version}. This might take some time...")
            raiden.install()
            continue

    return main_prompt()


def run_action_account_list():
    print("\nAvailable accounts:\n")
    for account in Account.get_user_accounts():
        print("\t", account.keystore_file_path, account.address)

    print("\n")
    return main_prompt()


def run_action_account_fund():
    account = prompt_account_selection()
    network = prompt_network_selection()
    ethereum_rpc_endpoint = prompt_ethereum_rpc_endpoint_selection(network=network)

    w3 = make_web3_provider(ethereum_rpc_endpoint.url, account)

    current_balance = account.get_ethereum_balance(w3)
    needed_funds = max(0, network.MINIMUM_ETHEREUM_BALANCE_REQUIRED - current_balance)

    if needed_funds > 0:
        if network.FAUCET_AVAILABLE:
            try:
                print(
                    f"Attempting to add funds to {account.address} on {network.capitalized_name}"
                )
                network.fund(account)
            except FundingError as exc:
                print(f"Failed: {exc}")
        else:
            print(f"Insufficience funds. Current balance is {current_balance}")
            print(
                f"Please send at least {needed_funds} to 0x{account.address} on "
                f"{network.capitalized_name}"
            )

            time_remaining = 60
            polling_interval = 1
            while (
                current_balance < network.MINIMUM_ETHEREUM_BALANCE_REQUIRED and time_remaining > 0
            ):
                time.sleep(polling_interval)
                print(f"Waiting for {time_remaining}s...")
                time_remaining -= polling_interval
                current_balance = account.get_ethereum_balance(w3)

            print("Balance is now", account.get_ethereum_balance(w3))

    return main_prompt()


def run_action_swap_kyber():
    account = prompt_account_selection()
    ethereum_rpc_endpoint = prompt_ethereum_rpc_endpoint_selection()
    w3 = make_web3_provider(ethereum_rpc_endpoint.url, account)

    kyber = Exchange.get_by_name("kyber")(w3=w3)
    amount = Wei(5 * (10 ** 18))
    kyber.buy_tokens(account, TokenAmount(amount, Erc20Token.find_by_sticker("RDN")))

    return main_prompt()


def run_action_launch_raiden():
    selected_setup = prompt(
        [
            {
                "name": "configuration",
                "type": "list",
                "message": Messages.input_launch_configuration,
                "choices": [
                    {"name": f"{pretty_print_configuration(cfg)}", "value": cfg}
                    for cfg in RaidenConfigurationFile.get_available_configurations()
                ],
            },
            {
                "name": "raiden",
                "type": "list",
                "message": Messages.input_launch_release,
                "choices": [
                    {"name": raiden.release, "value": raiden} for raiden in RELEASE_MAP.values()
                ],
            },
        ]
    )

    raiden = selected_setup["raiden"]
    configuration = selected_setup["configuration"]

    print("Launching raiden...")
    raiden.launch(configuration)
    print("Launch successful...")


def run_action_configuration_setup():
    account = prompt_account_selection()
    network = prompt_network_selection()

    ethereum_rpc_questions = [
        {
            "name": "will_use_infura",
            "type": "confirm",
            "default": True,
            "message": Messages.input_use_infura,
        },
        {
            "name": "infura_project_id",
            "type": "input",
            "message": Messages.input_ethereum_infura_project_id,
            "when": lambda answers: answers["will_use_infura"],
            "filter": lambda answer: answer.strip(),
            "validator": InfuraProjectIdValidator,
        },
        {
            "name": "ethereum_rpc_endpoint",
            "type": "input",
            "message": Messages.input_ethereum_rpc_endpoint,
            "when": lambda answers: not answers["will_use_infura"],
        },
    ]

    ethereum_rpc_answers = validate_prompt(ethereum_rpc_questions)

    if ethereum_rpc_answers["will_use_infura"]:
        project_id = ethereum_rpc_answers["infura_project_id"]
        client_rpc_endpoint = Infura.make(network, project_id).url
    else:
        client_rpc_endpoint = ethereum_rpc_answers["ethereum_rpc_endpoint"]

    user_deposit_contract_address = get_contract_address(network.chain_id, CONTRACT_USER_DEPOSIT)

    config = RaidenConfigurationFile(
        account=account,
        network=network,
        ethereum_client_rpc_endpoint=client_rpc_endpoint,
        user_deposit_contract_address=user_deposit_contract_address,
    )
    config.save()

    return main_prompt()


def run_action_account_create():
    passphrase = single_question_prompt({"type": "password", "message": Messages.input_passphrase})

    Account.create(passphrase)
    return main_prompt()


def main():
    current_prompt = main_prompt()
    while current_prompt:
        answer = single_question_prompt(current_prompt)
        action = {
            Messages.action_launch_raiden: run_action_launch_raiden,
            Messages.action_configuration_setup: run_action_configuration_setup,
            Messages.action_configuration_list: run_action_configuration_list,
            Messages.action_account_create: run_action_account_create,
            Messages.action_account_list: run_action_account_list,
            Messages.action_account_fund: run_action_account_fund,
            Messages.action_release_manager: run_action_release_manager,
            Messages.action_swap_kyber: run_action_swap_kyber,
            Messages.action_quit: lambda: None,
        }.get(answer, print_invalid_option)
        current_prompt = action()


if __name__ == "__main__":
    main()
