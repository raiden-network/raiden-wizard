from whaaaaat import prompt

from .. import base


class Messages:
    action_launch_raiden = "Launch raiden."
    action_create_config = "Create new raiden configuration."
    action_create_account = "Create new ethereum account."
    action_list_accounts = "List existing accounts."
    action_list_configurations = "List existing configuration files."
    action_quit = "Quit this raiden launcher."
    input_passphrase = "Please provide a passphrase:"
    input_use_infura = "Use infura.io for ethereum chain operations?"


def main_prompt():
    available_choices = [
        Messages.action_create_config,
        Messages.action_create_account,
        Messages.action_quit,
    ]

    if base.RaidenConfigurationFile.get_available_configurations():
        available_choices.insert(0, Messages.action_launch_raiden)

    return {
        "type": "list",
        "message": "What would you like to do?",
        "choices": available_choices,
    }


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
    questions = [
        {
            "name": "account",
            "type": "list",
            "message": "Which account would you like to use?",
            "choices": [
                f"{account.keystore_file_path} - {account.address}"
                for account in base.Account.get_user_accounts()
            ],
        },
        {
            "name": "network",
            "type": "list",
            "choices": base.Network.get_network_names(),
            "message": "Which network would you like to use?",
        },
        {
            "name": "will_use_infura",
            "type": "confirm",
            "default": True,
            "message": Messages.input_use_infura,
        },
    ]

    answers = prompt(questions)

    print(answers)
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
            Messages.action_quit: lambda: None,
        }.get(answer, print_invalid_option)
        current_prompt = action()
