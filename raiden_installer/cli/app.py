from raiden_contracts.constants import CONTRACT_USER_DEPOSIT

from whaaaaat import ValidationError, Validator, prompt

from .. import RAIDEN_CLIENT_DEFAULT_CLASS, base


class Messages:
    action_launch_raiden = "Launch raiden"
    action_account_create = "Create new ethereum account"
    action_account_list = "List existing ethereum accounts"
    action_account_fund = "Add funds to account (some test networks only)"
    action_configuration_setup = "Create new raiden setup"
    action_configuration_list = "List existing raiden setups"
    action_release_manager = "Install/Uninstall raiden releases"
    action_release_list_installed = "List installed raiden releases"
    action_release_update_info = "Check for updates in raiden"
    action_quit = "Quit this raiden launcher"
    input_account_select = "Please select account"
    input_network_select = "Which ethereum network to use?"

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
        if not base.Infura.is_valid_project_id(self.text):
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
                for account in base.Account.get_user_accounts()
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
    networks = network_list or base.Network.all()
    return single_question_prompt(
        {
            "name": "network",
            "type": "list",
            "message": Messages.input_network_select,
            "choices": [
                {"name": network.capitalized_name, "value": network}
                for network in networks
            ],
        }
    )


def print_invalid_option():
    print("Invalid option. Try again")


def main_prompt():

    configuration_choices = [Messages.action_configuration_setup]
    account_choices = [Messages.action_account_create]
    raiden_release_management_choices = [Messages.action_release_manager]

    if base.RaidenConfigurationFile.get_launchable_configurations():
        configuration_choices.insert(0, Messages.action_launch_raiden)

    if base.RaidenConfigurationFile.get_available_configurations():
        configuration_choices.append(Messages.action_configuration_list)

    if base.Account.get_user_accounts():
        account_choices.append(Messages.action_account_list)
        account_choices.append(Messages.action_account_fund)

    available_choices = (
        configuration_choices + account_choices + raiden_release_management_choices
    )

    available_choices.append(Messages.action_quit)

    return {
        "type": "list",
        "message": "What would you like to do?",
        "choices": available_choices,
    }


def run_action_configuration_list():
    print(
        "\nAvailable setups (Not necessarily satisfying conditions for running raiden)\n"
    )
    for config in base.RaidenConfigurationFile.get_available_configurations():
        print("\t", config.short_description)

    print("\n")
    return main_prompt()


def run_action_release_manager():

    all_releases = {
        raiden.release: raiden
        for raiden in RAIDEN_CLIENT_DEFAULT_CLASS.get_available_releases()
    }

    release_selection = prompt(
        {
            "name": "releases",
            "type": "checkbox",
            "message": Messages.input_release_manager,
            "choices": [
                {
                    "name": raiden.release,
                    "value": raiden,
                    "checked": raiden.is_installed,
                }
                for raiden in all_releases.values()
            ],
        }
    )

    to_install = [release_name for release_name in release_selection["releases"]]

    for raiden in all_releases.values():
        if raiden.is_installed and raiden.release not in to_install:
            print(f"Uninstalling {raiden.release}")
            raiden.uninstall()
            continue

        if not raiden.is_installed and raiden.release in to_install:
            print(f"Installing {raiden.release}. This might take some time...")
            raiden.install()
            continue

    return main_prompt()


def run_action_account_list():
    print("\nAvailable accounts:\n")
    for account in base.Account.get_user_accounts():
        print("\t", account.keystore_file_path, account.address)

    print("\n")
    return main_prompt()


def run_action_account_fund():
    account = prompt_account_selection(validate_passphrase=False)
    network = prompt_network_selection(
        network_list=[
            network for network in base.Network.all() if network.FAUCET_AVAILABLE
        ]
    )

    print(f"Attempting to add funds to {account.address} on {network.capitalized_name}")

    try:
        network.fund(account)
    except base.FundingError as exc:
        print(f"Failed: {exc}")

    return main_prompt()


def run_action_launch_raiden():
    selected_setup = prompt(
        [
            {
                "name": "configuration",
                "type": "list",
                "message": Messages.input_launch_configuration,
                "choices": [
                    {"name": f"{cfg.short_description}", "value": cfg}
                    for cfg in base.RaidenConfigurationFile.get_launchable_configurations()
                ],
            },
            {
                "name": "raiden",
                "type": "list",
                "message": Messages.input_launch_release,
                "choices": [
                    {"name": raiden.release, "value": raiden}
                    for raiden in RAIDEN_CLIENT_DEFAULT_CLASS.get_installed_releases()
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
        client_rpc_endpoint = base.build_infura_url(network, project_id)
    else:
        client_rpc_endpoint = ethereum_rpc_answers["ethereum_rpc_endpoint"]

    user_deposit_contract_address = network.get_contract_address(CONTRACT_USER_DEPOSIT)

    config = base.RaidenConfigurationFile(
        account=account,
        network=network,
        ethereum_client_rpc_endpoint=client_rpc_endpoint,
        user_deposit_contract_address=user_deposit_contract_address,
    )
    config.save()

    ethereum_rpc_provider = base.EthereumRPCProvider.make_from_url(client_rpc_endpoint)

    token_contract = base.TokenContract(
        web3_provider=ethereum_rpc_provider.make_web3_provider(account),
        account=account,
        user_deposit_contract_address=user_deposit_contract_address,
    )

    token_contract.mint(token_contract.TOKEN_AMOUNT)

    return main_prompt()


def run_action_account_create():
    passphrase = single_question_prompt(
        {"type": "password", "message": Messages.input_passphrase}
    )

    base.Account.create(passphrase)
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
            Messages.action_quit: lambda: None,
        }.get(answer, print_invalid_option)
        current_prompt = action()


if __name__ == "__main__":
    main()
