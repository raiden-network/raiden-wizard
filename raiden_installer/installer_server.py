import socket
import webbrowser
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for
)


app = Flask(__name__)


global keystore_pwd
global network
global proj_id


@app.route('/', methods=['GET', 'POST'])
def user_input():
    if request.method == 'POST':
        keystore_pwd = request.form['keystore-pwd']
        network = request.form['network']
        proj_id = request.form['proj-id']

        return redirect(url_for('installation'))
    return render_template('user-input.html')


@app.route('/installation', methods=['GET'])
def installation():
    return render_template('installation.html')


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