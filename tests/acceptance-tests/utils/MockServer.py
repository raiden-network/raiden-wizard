"""Pretenders mock server configuration for Infura.io requests.

The file configures commonly used endpoints of the Infura.io request and returns
mock responses for them, avoiding requesting the actual API.

It's importable as a library in .robot files::

    ~/raideninstaller$ cat acceptance-tests/<iteration>/test.robot
    *** Settings ***
    Library     ../utils/MockServer.py

    *** Keywords ***
    My Custom Keyword
        ${host}     ${PORT} =   Server Address
        Setup Normal


"""
from pretenders.client.http import HTTPMock
from pretenders.constants import FOREVER

ROBOT_LIBRARY_DOC_FORMAT = 'reST'


class MockServer:
    def __init__(self, host='localhost', port=8000):
        self._address = host, port
        self.server = HTTPMock(host, port)

    def server_address(self):
        return self._address

    def setup_normal(self):
        self.server.reset()

        # FIXME: Endpoint is a placeholder!
        self.server.when("GET /important_data").reply('OK', status=200, times=FOREVER)

    def setup_error(self):
        self.server.reset()

        # FIXME: Endpoint is a placeholder!
        self.server.when("GET /important_data").reply('ERROR', status=500, times=FOREVER)
