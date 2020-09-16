import asyncio
import json
import os
from unittest.mock import patch

import pytest
from eth_utils import add_0x_prefix
from tests.constants import TESTING_TEMP_FOLDER
from tests.fixtures import create_account, test_account, test_password
from tests.utils import empty_account
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect

from raiden_installer import load_settings
from raiden_installer.account import find_keystore_folder_path
from raiden_installer.base import RaidenConfigurationFile
from raiden_installer.ethereum_rpc import Infura, make_web3_provider
from raiden_installer.network import Network
from raiden_installer.raiden import RaidenClient
from raiden_installer.shared_handlers import get_passphrase, set_passphrase
from raiden_installer.tokens import Erc20Token
from raiden_installer.transactions import get_token_balance, get_token_deposit
from raiden_installer.web import get_app
from raiden_installer.web_testnet import get_app as get_app_testnet

INFURA_PROJECT_ID = os.getenv("TEST_RAIDEN_INSTALLER_INFURA_PROJECT_ID")

UNLOCK_PAGE_HEADLINE = "<h2>Unlock your Raiden Account</h2>"


pytestmark = pytest.mark.skipif(not INFURA_PROJECT_ID, reason="missing configuration for infura")


def successful_html_response(response):
    return response.code == 200 and response.headers["Content-Type"] == "text/html; charset=UTF-8"


def successful_json_response(response):
    return (response.code == 200 and
            response.headers["Content-Type"] == "application/json")


def is_unlock_page(body):
    return UNLOCK_PAGE_HEADLINE in body.decode("utf-8")


def check_balances(w3, account, settings, check_func):
    balance = account.get_ethereum_balance(w3)

    service_token = Erc20Token.find_by_ticker(settings.service_token.ticker, settings.network)
    udc_balance = get_token_deposit(w3, account, service_token)

    transfer_token = Erc20Token.find_by_ticker(settings.transfer_token.ticker, settings.network)
    transfer_token_balance = get_token_balance(w3, account, transfer_token)

    return (
        check_func(balance.as_wei) and
        check_func(udc_balance.as_wei) and
        check_func(transfer_token_balance.as_wei)
    )


class SharedHandlersTests:
    @pytest.fixture
    def infura(self, test_account, network_name):
        assert INFURA_PROJECT_ID
        network = Network.get_by_name(network_name)
        return Infura.make(network, INFURA_PROJECT_ID)

    @pytest.fixture
    def settings(self, settings_name):
        return load_settings(settings_name)

    @pytest.fixture
    def patch_config_folder(self, monkeypatch):
        monkeypatch.setattr(
            RaidenConfigurationFile,
            "FOLDER_PATH",
            TESTING_TEMP_FOLDER.joinpath("config")
        )

    @pytest.fixture
    def config(self, patch_config_folder, test_account, infura, settings):
        config = RaidenConfigurationFile(
            test_account.keystore_file_path,
            settings,
            infura.url,
        )
        config.save()
        yield config
        config.path.unlink()

    @pytest.fixture
    def unlocked(self, test_password):
        set_passphrase(test_password)
        yield
        set_passphrase(None)

    @pytest.fixture
    def ws_client(self, http_client, http_port):
        loop = asyncio.get_event_loop()
        url = f"ws://localhost:{http_port}/ws"
        client = loop.run_until_complete(websocket_connect(url))
        yield client

        client.close()
        for task in asyncio.all_tasks(loop):
            task.cancel()

    @pytest.mark.gen_test
    def test_index_handler(self, http_client, base_url):
        response = yield http_client.fetch(base_url)
        assert successful_html_response(response)

    @pytest.mark.gen_test
    def test_create_wallet_handler(self, http_client, base_url):
        response = yield http_client.fetch(f"{base_url}/create_wallet")
        assert successful_html_response(response)

    @pytest.mark.gen_test
    def test_setup_handler(self, http_client, base_url, test_account):
        response = yield http_client.fetch(f"{base_url}/setup/{test_account.keystore_file_path}")
        assert successful_html_response(response)

    @pytest.mark.gen_test
    def test_account_handler(self, http_client, base_url, config, unlocked):
        response = yield http_client.fetch(f"{base_url}/account/{config.file_name}")
        assert successful_html_response(response)
        assert not is_unlock_page(response.body)

    @pytest.mark.gen_test
    def test_locked_account_handler(self, http_client, base_url, config):
        response = yield http_client.fetch(f"{base_url}/account/{config.file_name}")
        assert successful_html_response(response)
        assert is_unlock_page(response.body)

    @pytest.mark.gen_test
    def test_launch_handler(self, http_client, base_url, config, unlocked):
        response = yield http_client.fetch(f"{base_url}/launch/{config.file_name}")
        assert successful_html_response(response)
        assert not is_unlock_page(response.body)

    @pytest.mark.gen_test
    def test_locked_launch_handler(self, http_client, base_url, config):
        response = yield http_client.fetch(f"{base_url}/launch/{config.file_name}")
        assert successful_html_response(response)
        assert is_unlock_page(response.body)

    @pytest.mark.gen_test
    def test_keystore_handler(self, http_client, base_url, test_account, config):
        response = yield http_client.fetch(
            f"{base_url}/keystore/{config.file_name}/{test_account.keystore_file_path.name}"
        )
        json_response = json.loads(response.body)
        assert successful_json_response(response)
        assert add_0x_prefix(json_response["address"]).lower() == test_account.address.lower()

    @pytest.mark.gen_test(timeout=10)
    def test_gas_price_handler(self, http_client, base_url, config):
        response = yield http_client.fetch(
            f"{base_url}/gas_price/{config.file_name}"
        )
        json_response = json.loads(response.body)
        assert successful_json_response(response)
        assert json_response["gas_price"] > 0

    @pytest.mark.gen_test
    def test_configuration_item_handler(self, http_client, base_url, config):
        response = yield http_client.fetch(
            f"{base_url}/api/configuration/{config.file_name}"
        )
        json_response = json.loads(response.body)
        assert successful_json_response(response)
        assert json_response["file_name"] == config.file_name
        assert json_response["account"] == config.account.address
        assert json_response["network"] == config.network.name
        assert json_response["balance"]["ETH"]["as_wei"] == 0
        assert json_response["balance"]["service_token"]["as_wei"] == 0
        assert json_response["balance"]["transfer_token"]["as_wei"] == 0

    # Websocket methods tests

    @pytest.mark.gen_test
    def test_create_wallet(self, ws_client, test_password, test_account):
        with patch(
            "raiden_installer.account.Account.create",
            return_value=test_account
        ) as mock_create_account:
            data = {
                "method": "create_wallet",
                "passphrase1": test_password,
                "passphrase2": test_password
            }
            ws_client.write_message(json.dumps(data))

            message = json.loads((yield ws_client.read_message()))
            assert message["type"] == "status-update"

            message = json.loads((yield ws_client.read_message()))
            assert message["type"] == "redirect"
            assert message["redirect_url"] == f"/setup/{test_account.keystore_file_path}"

            mock_create_account.assert_called_once_with(
                find_keystore_folder_path(),
                test_password
            )

    @pytest.mark.gen_test
    def test_unlock(self, ws_client, test_password, test_account):
        data = {
            "method": "unlock",
            "passphrase": test_password,
            "keystore_file_path": str(test_account.keystore_file_path),
            "return_to": f"/setup/{test_account.keystore_file_path}"
        }
        ws_client.write_message(json.dumps(data))

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "redirect"
        assert message["redirect_url"] == f"/setup/{test_account.keystore_file_path}"
        assert get_passphrase() == test_password

        set_passphrase(None)

    @pytest.mark.gen_test
    def test_unlock_with_wrong_passphrase(self, ws_client, test_password, test_account):
        data = {
            "method": "unlock",
            "passphrase": "wrong" + test_password,
            "keystore_file_path": str(test_account.keystore_file_path),
            "return_to": f"/setup/{test_account.keystore_file_path}"
        }
        ws_client.write_message(json.dumps(data))

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "error-message"
        assert get_passphrase() == None

    @pytest.mark.gen_test
    def test_setup(
        self,
        ws_client,
        test_account,
        infura,
        network_name,
        patch_config_folder,
        settings
    ):
        data = {
            "method": "setup",
            "endpoint": infura.url,
            "network": network_name,
            "account_file": str(test_account.keystore_file_path)
        }
        ws_client.write_message(json.dumps(data))

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "status-update"

        config_file_name = f"config-{test_account.address}-{settings.name}.toml"
        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "redirect"
        assert message["redirect_url"] == f"/account/{config_file_name}"

        config = RaidenConfigurationFile.get_by_filename(config_file_name)
        assert config.account.keystore_file_path == test_account.keystore_file_path
        assert config.settings == settings
        assert config.ethereum_client_rpc_endpoint == infura.url
        assert config.routing_mode == settings.routing_mode
        assert config.enable_monitoring == settings.monitoring_enabled

        config.path.unlink()

    @pytest.mark.gen_test
    def test_setup_with_invalid_network(
        self,
        ws_client,
        test_account,
        infura,
        patch_config_folder,
        settings
    ):
        data = {
            "method": "setup",
            "endpoint": infura.url,
            "network": "invalid network",
            "account_file": str(test_account.keystore_file_path)
        }
        ws_client.write_message(json.dumps(data))

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "error-message"

        with pytest.raises(ValueError):
            RaidenConfigurationFile.get_by_filename(
                f"config-{test_account.address}-{settings.name}.toml"
            )

    @pytest.mark.gen_test
    def test_setup_with_invalid_endpoint(
        self,
        ws_client,
        test_account,
        network_name,
        patch_config_folder,
        settings
    ):
        data = {
            "method": "setup",
            "endpoint": "not.valid",
            "network": network_name,
            "account_file": str(test_account.keystore_file_path)
        }
        ws_client.write_message(json.dumps(data))

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "error-message"

        with pytest.raises(ValueError):
            RaidenConfigurationFile.get_by_filename(
                f"config-{test_account.address}-{settings.name}.toml"
            )

    @pytest.mark.gen_test
    def test_launch(self, ws_client, config, unlocked):
        with patch(
            "raiden_installer.raiden.RaidenClient.get_client",
            spec=RaidenClient
        ) as mock_get_client:
            mock_client = mock_get_client()
            mock_client.is_installed = False
            mock_client.is_running = False

            data = {
                "method": "launch",
                "configuration_file_name": config.file_name,
            }
            ws_client.write_message(json.dumps(data))

            for _ in range(3):
                message = json.loads((yield ws_client.read_message()))
                assert message["type"] == "status-update"

            message = json.loads((yield ws_client.read_message()))
            assert message["type"] == "task-complete"

            message = json.loads((yield ws_client.read_message()))
            assert message["type"] == "redirect"
            assert message["redirect_url"] == RaidenClient.WEB_UI_INDEX_URL

            mock_client.install.assert_called_once()
            mock_client.launch.assert_called_once()
            mock_client.wait_for_web_ui_ready.assert_called_once()

    @pytest.mark.gen_test
    def test_locked_launch(self, ws_client, config):
        with patch(
            "raiden_installer.raiden.RaidenClient.get_client",
            spec=RaidenClient
        ) as mock_get_client:
            mock_client = mock_get_client()
            mock_client.is_installed = False
            mock_client.is_running = False

            data = {
                "method": "launch",
                "configuration_file_name": config.file_name,
            }
            ws_client.write_message(json.dumps(data))

            message = json.loads((yield ws_client.read_message()))
            assert message["type"] == "error-message"

            mock_client.install.assert_not_called()
            mock_client.launch.assert_not_called()
            mock_client.wait_for_web_ui_ready.assert_not_called()


class TestWeb(SharedHandlersTests):
    @pytest.fixture
    def app(self):
        return get_app()

    @pytest.fixture
    def network_name(self):
        return "mainnet"

    @pytest.fixture
    def settings_name(self):
        return "mainnet"

    @pytest.mark.gen_test
    def test_swap_handler(self, http_client, base_url, config, settings, unlocked):
        response = yield http_client.fetch(
            f"{base_url}/swap/{config.file_name}/{settings.service_token.ticker}"
        )
        assert successful_html_response(response)
        assert not is_unlock_page(response.body)

    @pytest.mark.gen_test
    def test_locked_swap_handler(self, http_client, base_url, config, settings):
        response = yield http_client.fetch(
            f"{base_url}/swap/{config.file_name}/{settings.service_token.ticker}"
        )
        assert successful_html_response(response)
        assert is_unlock_page(response.body)

    @pytest.mark.gen_test(timeout=15)
    def test_cost_estimation_handler(self, http_client, base_url, config, settings):
        exchange = "Kyber"
        currency = settings.transfer_token.ticker
        target_amount = 3
        data = {
            "exchange": exchange,
            "currency": currency,
            "target_amount": target_amount,
        }
        request = HTTPRequest(
            url=f"{base_url}/api/cost-estimation/{config.file_name}",
            method="POST",
            body=json.dumps(data)
        )
        response = yield http_client.fetch(request)
        json_response = json.loads(response.body)
        assert successful_json_response(response)
        assert json_response["exchange"] == exchange
        assert json_response["currency"] == currency
        assert json_response["target_amount"] == target_amount
        assert json_response["as_wei"] > 0


class TestWebTestnet(SharedHandlersTests):
    @pytest.fixture
    def app(self):
        return get_app_testnet()

    @pytest.fixture
    def network_name(self):
        return "goerli"

    @pytest.fixture
    def settings_name(self):
        return "demo_env"

    @pytest.mark.gen_test(timeout=900)
    def test_funding(self, ws_client, config, test_account, unlocked, settings):
        data = {
            "method": "fund",
            "configuration_file_name": config.file_name,
        }
        ws_client.write_message(json.dumps(data))

        for _ in range(2):
            message = json.loads((yield ws_client.read_message()))
            assert message["type"] == "status-update"

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "next-step"

        for _ in range(3):
            message = json.loads((yield ws_client.read_message()))
            assert message["type"] == "status-update"

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "next-step"

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "redirect"
        assert message["redirect_url"] == f"/launch/{config.file_name}"

        w3 = make_web3_provider(config.ethereum_client_rpc_endpoint, test_account)
        assert check_balances(w3, test_account, settings, lambda x: x > 0)

        empty_account(w3, test_account)

    @pytest.mark.gen_test
    def test_funding_with_invalid_config_file(
        self,
        ws_client,
        config,
        test_account,
        unlocked,
        settings
    ):
        data = {
            "method": "fund",
            "configuration_file_name": "invalid" + config.file_name,
        }
        ws_client.write_message(json.dumps(data))

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "error-message"

        w3 = make_web3_provider(config.ethereum_client_rpc_endpoint, test_account)
        assert check_balances(w3, test_account, settings, lambda x: x == 0)

    @pytest.mark.gen_test
    def test_locked_funding(self, ws_client, config, test_account, settings):
        data = {
            "method": "fund",
            "configuration_file_name": config.file_name,
        }
        ws_client.write_message(json.dumps(data))

        message = json.loads((yield ws_client.read_message()))
        assert message["type"] == "error-message"

        w3 = make_web3_provider(config.ethereum_client_rpc_endpoint, test_account)
        assert check_balances(w3, test_account, settings, lambda x: x == 0)
