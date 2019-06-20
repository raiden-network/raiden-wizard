import socket
import webbrowser
from flask import Flask


app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    return (
        '''
        Installer Server
        '''
    )


if __name__ == '__main__':
    new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    new_socket.bind(('127.0.0.1', 0))
    port = new_socket.getsockname()[1]

    # Jumps over port where Raiden will be running
    if port == 5001:
        port += 1

    new_socket.close()

    webbrowser.open_new(f'http://127.0.0.1:{port}/')
    app.run(host='127.0.0.1', port=f'{port}')