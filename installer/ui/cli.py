from whaaaaat import prompt

from .. import base


class Messages:
    action_launch_raiden = "Launch raiden"
    action_account_create = "Create new ethereum account"
    action_account_list = "List existing accounts"
    action_configuration_create = "Create new raiden setup"
    action_configuration_list = "List existing raiden setups"
    action_release_install_latest = "Install latest raiden release"
    action_release_manager = "Install/Uninstall raiden releases"
    action_release_list_installed = "List installed raiden releases"
    action_release_update_info = "Check for updates in raiden"
    action_quit = "Quit this raiden launcher"
    input_account_verify_passphrase = "Please provide the passphrase"
    input_release_manager = "Check/Uncheck all releases you want to install/unsinstall"
    input_passphrase = "Please provide a passphrase:"
    input_use_infura = "Use infura.io for ethereum chain operations?"
    input_ethereum_infura_project_id = "Please provide your Infura Project Id:"
    input_ethereum_rpc_endpoint = "Please provide the URL of your ethereum client RPC:"


def main_prompt():

    configuration_choices = [Messages.action_configuration_create]
    account_choices = [Messages.action_account_create]
    raiden_release_management_choices = [Messages.action_release_manager]

    latest_release = base.RaidenClient.get_latest_release()
    if not latest_release.is_installed:
        raiden_release_management_choices.insert(
            0, Messages.action_release_install_latest
        )

    if base.RaidenConfigurationFile.get_available_configurations():
        configuration_choices.insert(0, Messages.action_launch_raiden)
        configuration_choices.append(Messages.action_configuration_list)

    if base.Account.get_user_accounts():
        account_choices.insert(0, Messages.action_account_list)

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


def run_action_release_manager():
    release_selection = prompt(
        {
            "name": "releases",
            "type": "checkbox",
            "message": Messages.input_release_manager,
            "choices": [
                {"name": raiden.release, "checked": raiden.is_installed}
                for raiden in base.RaidenClient.get_available_releases()
            ],
        }
    )

    installed_releases = [r.release for r in base.RaidenClient.get_installed_releases()]

    to_install = set(release_selection["releases"]) - set(installed_releases)
    to_uninstall = set(installed_releases) - set(release_selection["releases"])

    for release in to_install:
        print(f"Installing {release}. This might take some time...")
        base.RaidenClient(release).install()

    for release in to_uninstall:
        print(f"Uninstalling {release}")
        base.RaidenClient(release).uninstall()

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


def run_action_launch_raiden():
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
            Messages.action_launch_raiden: run_action_launch_raiden,
            Messages.action_configuration_create: set_new_config_prompt,
            Messages.action_account_create: set_new_account_prompt,
            Messages.action_release_list_installed: list_installed_releases,
            Messages.action_release_install_latest: install_latest_release,
            Messages.action_release_manager: run_action_release_manager,
            Messages.action_quit: lambda: None,
        }.get(answer, print_invalid_option)
        current_prompt = action()
