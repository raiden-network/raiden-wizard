FROM python:3.7-stretch

# install dependencies
RUN apt-get update
RUN apt-get install -y git-core wget xz-utils build-essential automake pkg-config libtool libffi-dev python3-dev libgmp-dev

RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"



ADD ./requirements.txt /tmp
WORKDIR /tmp

RUN pip install -r requirements.txt && pip install "PyInstaller==3.5"

ADD . /raiden-wizard
WORKDIR /raiden-wizard

# build pyinstaller package
RUN pyinstaller --noconfirm --clean tools/pyinstaller/raiden_webapp.spec

# pack result to have a unique name to get it out of the container later
RUN cd dist && \
    tar -cvzf ./raiden_wizard_linux.tar.gz raiden_wizard && \
    mv raiden_wizard_linux.tar.gz ..
