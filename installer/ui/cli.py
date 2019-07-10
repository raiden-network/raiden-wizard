from whaaaaat import prompt

from .. import base


class Messages:
    action_launch_raiden = "Launch raiden."
    action_create_config = "Create new raiden setup."
    action_create_account = "Create new ethereum account."
    action_list_accounts = "List existing accounts."
    action_list_configurations = "List existing raiden setups."
    action_install_latest_release = "Install latest raiden release"
    action_manage_releases = "Install/Uninstall raiden releases"
    action_list_configurations = "List existing configuration files."
    action_list_installed_releases = "List installed raiden releases"
    action_quit = "Quit this raiden launcher."
    input_account_verify_passphrase = ("Please provide the passphrase",)
    input_passphrase = "Please provide a passphrase:"
    input_use_infura = "Use infura.io for ethereum chain operations?"
    input_ethereum_infura_project_id = "Please provide your Infura Project Id:"
    input_ethereum_rpc_endpoint = "Please provide the URL of your ethereum client RPC:"


def main_prompt():
    configuration_choices = [Messages.action_create_config]
    account_choices = [Messages.action_create_account]
    raiden_release_management_choices = [Messages.action_manage_releases]

    latest_release = base.RaidenClient.get_latest_release()
    if not latest_release.is_installed:
        raiden_release_management_choices.insert(
            0, Messages.action_install_latest_release
        )

    if base.RaidenConfigurationFile.get_available_configurations():
        configuration_choices.insert(0, Messages.action_launch_raiden)
        configuration_choices.append(Messages.action_list_configurations)

    if base.Account.get_user_accounts():
        account_choices.insert(0, Messages.action_list_accounts)

    available_choices = (
        configuration_choices + account_choices + raiden_release_management_choices
    )

    available_choices.append(Messages.action_quit)

    return {
        "type": "list",
        "message": "What would you like to do?",
        "choices": available_choices,
    }


def list_installed_releases():
    for raiden in base.RaidenClient.get_available_releases():
        print(f"{raiden.release} - Installed: {'Y' if raiden.is_installed else 'N'}")

    return main_prompt()


def install_latest_release():
    latest = base.RaidenClient.get_latest_release()
    if latest.is_installed:
        print(f"Raiden {latest.release} is already installed")
    else:
        print(
            f"Downloading and installing raiden {latest.release}. This may take some time"
        )
        latest.install()
        print("Installation Complete")

    return main_prompt()


def single_question_prompt(question_data: dict):
    key = "single_question"
    question_data["name"] = key

    return prompt(question_data).get(key)


def print_invalid_option():
    print("Invalid option. Try again")


def set_configuration_list_prompt():
    return {
        "type": "list",
        "message": "These are the available setups to launch raiden",
        "choices": [
            f"{cfg.short_description}"
            for cfg in base.RaidenConfigurationFile.get_available_configurations()
        ],
    }


def set_new_config_prompt():
    def get_keystore_file_path(answer):
        return answer.split(" - ")[0]

    passphrase_verified = False

    while not passphrase_verified:
        account_questions = [
            {
                "name": "keystore",
                "type": "list",
                "message": "Which account would you like to use?",
                "choices": [
                    f"{account.keystore_file_path} - {account.address}"
                    for account in base.Account.get_user_accounts()
                ],
                "filter": get_keystore_file_path,
            },
            {
                "name": "passphrase",
                "type": "password",
                "message": Messages.input_account_verify_passphrase,
            },
        ]

        account_answers = prompt(account_questions)
        passphrase = account_answers["passphrase"]
        account = base.Account(keystore_file_path=account_answers["keystore"])
        passphrase_verified = account.check_passphrase(passphrase)

    account.passphrase = passphrase

    network = single_question_prompt(
        {
            "name": "network",
            "type": "list",
            "choices": base.Network.get_network_names(),
            "message": "Which network would you like to use?",
            "default": "goerli",
            "filter": lambda answer: base.Network.get_by_name(answer),
        }
    )

    ethereum_rpc_questions = [
        {
            "name": "will_use_infura",
            "type": "confirm",
            "default": True,
            "message": Messages.input_use_infura,
        },
        {
            "name": "ethereum_rpc_endpoint",
            "type": "input",
            "message": Messages.input_ethereum_infura_project_id,
            "when": lambda answers: answers["will_use_infura"],
        },
        {
            "name": "ethereum_rpc_endpoint",
            "type": "input",
            "message": Messages.input_ethereum_rpc_endpoint,
            "when": lambda answers: not answers["will_use_infura"],
        },
    ]

    ethereum_rpc_answers = prompt(ethereum_rpc_questions)

    if ethereum_rpc_answers["will_use_infura"]:
        project_id = ethereum_rpc_answers["ethereum_rpc_endpoint"]

        client_rpc_endpoint = f"https://{network.name}.infura.io/v3/{project_id}"
    else:
        client_rpc_endpoint = ethereum_rpc_answers["ethereum_rpc_endpoint"]

    config = base.RaidenConfigurationFile(
        account=account,
        network=network,
        ethereum_client_rpc_endpoint=client_rpc_endpoint,
    )
    config.save()

    return main_prompt()


def set_new_account_prompt():
    passphrase = single_question_prompt(
        {"type": "password", "message": Messages.input_passphrase}
    )

    base.Account.create(passphrase)
    return main_prompt()


def run():
    current_prompt = main_prompt()
    while current_prompt:
        answer = single_question_prompt(current_prompt)
        action = {
            Messages.action_launch_raiden: set_configuration_list_prompt,
            Messages.action_create_config: set_new_config_prompt,
            Messages.action_create_account: set_new_account_prompt,
            Messages.action_list_installed_releases: list_installed_releases,
            Messages.action_install_latest_release: install_latest_release,
            Messages.action_quit: lambda: None,
        }.get(answer, print_invalid_option)
        current_prompt = action()
