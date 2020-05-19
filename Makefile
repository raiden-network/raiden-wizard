help:
	@echo "bundle-docker - create standalone executable with PyInstaller via a docker container"


bundle-docker:
	docker build -t pyinstallerbuilder -f tools/docker/build.Dockerfile .
	-(docker rm builder)
	docker create --name builder pyinstallerbuilder
	mkdir -p dist/
	docker cp builder:/raiden-wizard/raiden_wizard_linux.tar.gz dist/raiden_wizard_linux.tar.gz
	docker rm builder
