from whaaaaat import prompt, Validator, ValidationError

from .. import base


class Messages:
    action_launch_raiden = "Launch raiden"
    action_account_create = "Create new ethereum account"
    action_account_list = "List existing ethereum accounts"
    action_configuration_create = "Create new raiden setup"
    action_configuration_list = "List existing raiden setups"
    action_release_manager = "Install/Uninstall raiden releases"
    action_release_list_installed = "List installed raiden releases"
    action_release_update_info = "Check for updates in raiden"
    action_quit = "Quit this raiden launcher"
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
        if not base.is_valid_infura_project_id(self.text):
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


def print_invalid_option():
    print("Invalid option. Try again")


def main_prompt():

    configuration_choices = [Messages.action_configuration_create]
    account_choices = [Messages.action_account_create]
    raiden_release_management_choices = [Messages.action_release_manager]

    if base.RaidenConfigurationFile.get_launchable_configurations():
        configuration_choices.insert(0, Messages.action_launch_raiden)

    if base.RaidenConfigurationFile.get_available_configurations():
        configuration_choices.append(Messages.action_configuration_list)

    if base.Account.get_user_accounts():
        account_choices.append(Messages.action_account_list)

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
        try:
            raiden_client = base.RaidenClient(release)
            raiden_client.install()
        except (base.InstallerError, OSError) as exc:
            print(f"Failed to install {release}: {exc}")
            try:
                base.RaidenClient.get_available_releases.clear_cache()
                raiden_client.install_path().unlink()
            except Exception:
                pass

    for release in to_uninstall:
        print(f"Uninstalling {release}")
        base.RaidenClient(release).uninstall()

    return main_prompt()


def run_action_account_list():
    print("\nAvailable accounts:\n")
    for account in base.Account.get_user_accounts():
        print("\t", account.keystore_file_path, account.address)

    print("\n")
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
                    for raiden in base.RaidenClient.get_installed_releases()
                ],
                "filter": lambda answer: base.RaidenClient(answer),
            },
        ]
    )

    raiden = selected_setup["raiden"]
    configuration = selected_setup["configuration"]

    print("Launching raiden...")
    raiden.launch(configuration)
    print("Launch successful...")


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


def main():
    current_prompt = main_prompt()
    while current_prompt:
        answer = single_question_prompt(current_prompt)
        action = {
            Messages.action_launch_raiden: run_action_launch_raiden,
            Messages.action_configuration_create: set_new_config_prompt,
            Messages.action_configuration_list: run_action_configuration_list,
            Messages.action_account_create: set_new_account_prompt,
            Messages.action_account_list: run_action_account_list,
            Messages.action_release_manager: run_action_release_manager,
            Messages.action_quit: lambda: None,
        }.get(answer, print_invalid_option)
        current_prompt = action()


if __name__ == "__main__":
    main()