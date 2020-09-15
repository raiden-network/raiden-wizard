import asyncio
import json
import os

import pytest
from eth_utils import add_0x_prefix
from tests.constants import TESTING_TEMP_FOLDER
from tests.fixtures import create_account, test_account, test_password
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect

from raiden_installer import load_settings
from raiden_installer.base import RaidenConfigurationFile
from raiden_installer.ethereum_rpc import Infura
from raiden_installer.network import Network
from raiden_installer.shared_handlers import set_passphrase
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
    def config(self, test_account, infura, settings):
        RaidenConfigurationFile.FOLDER_PATH = TESTING_TEMP_FOLDER.joinpath("config")
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

    @pytest.mark.gen_test(timeout=10)
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
