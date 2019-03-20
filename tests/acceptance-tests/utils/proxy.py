"""
Redirect requests to external APIs and URLs to our Pretenders server.
"""

from mitmproxy import http


PRETENDERS_SERVER = 'localhost:8000'
REDIRECTS = ['infura.io']


def request(flow: http.HTTPFlow) -> None:
    # pretty_host takes the "Host" header of the request into account,
    # which is useful in transparent mode where we usually only have the IP
    # otherwise.
    if flow.request.pretty_host in REDIRECTS:
        flow.request.host = PRETENDERS_SERVER
