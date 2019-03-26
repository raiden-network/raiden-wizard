.PHONY: install run package-master package-latest package-release

dev-setup:

help:
	@echo "install - Install the requirements for development."
	@echo "run - Run the installer."
	@echo "binary - Create a single-file executable."

install:
	pip install -r requirements-dev.txt

run: install
	python raideninstaller

# Create an executable (single file).
binary:
	pyinstaller raideninstaller/__main__.py --clean --onefile --name raiden-installer-LATEST

