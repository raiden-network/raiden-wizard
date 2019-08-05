# Quick Start
Raiden is a scalable off-chain token payment solution for Ethereum. Running your very own Raiden node takes only five minutes with the Raiden Wizard.

## Get Started
This guide will teach you how to:
* [Download the Raiden Wizard](#download-the-raiden-wizard)
* [Setup and run Raiden](#setup-and-run-raiden)
* [Relaunch Raiden](#relaunch-raiden)
* [Get a Infura Project ID](#get-a-infura-project-id)
* [Handle issues](#handle-issues)

## Download the Raiden Wizard
Download the Raiden Wizard for either macOS or Linux.

[macOS download](https://github.com/raiden-network/raiden-installer/releases/download/v0.100.5-dev0/raiden_wizard.macOS.zip)

[Linux download](https://github.com/raiden-network/raiden-installer/releases/download/v0.100.5-dev0/raiden_wizard.linux-gnu.zip)

## Setup and Run Raiden
1. Extract and open the __Raiden Wizard__ file. The Wizard will launch in your default browser.
2. Insert your Infura Project ID. Don't have a Infura Project ID? Learn how to get one in the [section below](#get-a-infura-project-id).
3. Click __"Create New Configuration"__ to configure, install and launch the latest Raiden.

>The setup process can take up to five minutes, make sure not to close the browser.

__Congratulations! You're now ready to start interacting with Raiden!__ 🎉

![The Raiden Wizard setup process](https://drive.google.com/file/d/1G3Ick5z7hEJWYfGh2hSSvKN5TwgPmEC7/view?usp=sharing)

To get an overview of the web interface:

[Watch this video on the web interface](https://www.youtube.com/watch?v=ASWeFdHDK-E)

[Read this tutorial about the web interface](https://raiden-network.readthedocs.io/en/stable/webui_tutorial.html)

[Read the developer API guide](https://raiden-network.readthedocs.io/en/stable/rest_api.html)

## Relaunch Raiden
* Open the __Raiden Wizard__ file, you will find two ways of relaunching Raiden.

    1. Click the __"Launch"__ button next to a configuration you already created.
    2. Repeat the steps from [Setup and Run Raiden](#setup-and-run-raiden) to create a new configuratio.

> Each new configuration created will be added to the list and currently you can't delete configurations from the Wizard. Read more under [Handle Issues](#handle-issues).

## Get a Infura Project ID
1. Visit [infura.io](https://infura.io/) and sign up for a new account.
2. Create a new project.
3. View your project and you'll find the Project ID under the __KEYS__ tab.

![Steps to get a Infura Project ID](https://drive.google.com/file/d/1UnTF6SLKy7DL14IMqM6O3AsCB2dwuPes/view?usp=sharing)

> __What is Infura and why do I need a Project ID?__
>
> By using Infura you don't have to worry about syncing the blockchain on your own system. You can simply access all test networks and the Ethereum mainnet through the API endpoints provided by Infura.
>
>The Raiden Wizard sets up a Raiden node on top of Infura and your Project ID works as a way to authenticate your access to Infura.

## Handle Issues
The Raiden Wizard is in an early stage of implementation. In this section you will learn how to handle known issues.

> __Important__
>
> The Raiden Wizard will display an __*Internal Server Error*__ if an invalid Project ID is provided. To solve this you have to [manually delete the configuration](#delete-configuration-files) file that got created.
### Stop Raiden from Running
* __Mac__
    * Use the Activity Monitor app for stopping Raiden.
* __Linux__
    * Use any Linux process manager for stopping Raiden.

### Delete Configuration Files
* __Mac__
    1. Navigate to `/Users/<username>/.local/share/raiden/`
    2. Delete desired __.toml__ file/files.

* __Linux__
    1. Navigate to `/home/<username>/.local/raiden/`
    2. Delete desired __.toml__ file/files.
