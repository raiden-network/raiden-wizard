help:
	@echo "bundle-docker - create standalone executable with PyInstaller via a docker container"

clean:
	rm -r build/ dist/

bundle-docker:
	mkdir -p dist/
	# build for mainnet
	docker build -t pyinstallerbuilder -f tools/docker/build.Dockerfile .
	-(docker rm builder)
	docker create --name builder pyinstallerbuilder
	docker cp builder:/raiden-wizard/raiden_wizard_linux.tar.gz dist/raiden_wizard_mainnet_linux.tar.gz
	docker rm builder
	# build for goerli
	docker build --build-arg RAIDEN_INSTALLER_BUILD_ENTRY_SCRIPT="web_testnet.py" -t pyinstallerbuilder_goerli -f tools/docker/build.Dockerfile .
	-(docker rm builder_goerli)
	docker create --name builder_goerli pyinstallerbuilder_goerli
	docker cp builder_goerli:/raiden-wizard/raiden_wizard_linux.tar.gz dist/raiden_wizard_goerli_linux.tar.gz
	docker rm builder_goerli

build-mac: clean
	pyinstaller --noconfirm --clean tools/pyinstaller/raiden_webapp.spec
	tar -czf raiden_wizard_mainnet_macOS-1.0.x.tar.gz dist/raiden_wizard
	rm dist/raiden_wizard
	RAIDEN_INSTALLER_BUILD_ENTRY_SCRIPT="web_testnet.py" pyinstaller --noconfirm --clean tools/pyinstaller/raiden_webapp.spec
	tar -czf raiden_wizard_goerli_macOS-1.0.x.tar.gz dist/raiden_wizard
	rm dist/raiden_wizard
