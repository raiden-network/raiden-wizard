const RAMP_BALANCE_TIMEOUT = 300000;

let neededEthAmount = ETHEREUM_REQUIRED_AMOUNT;

function runFunding(configurationFileName) {
  let message = {
    method: "fund",
    configuration_file_name: configurationFileName,
  };
  WEBSOCKET.send(JSON.stringify(message));
  toggleView();
}

function showRamp() {
  const ramp = new rampInstantSdk.RampInstantSDK({
    hostAppName: "Raiden Wizard",
    hostLogoUrl:
      "https://raw.githubusercontent.com/raiden-network/raiden-wizard/develop/resources/static/images/raiden_logo_black.svg",
    hostApiKey: "wa2447zu7yrgarvc6463kuocyyde9cfq9trwjj9z",
    swapAmount: ETHEREUM_REQUIRED_AMOUNT.toString(),
    swapAsset: "ETH",
    userAddress: TARGET_ADDRESS,
  });

  const purchaseCreatedCallback = () => {
    ramp.unsubscribe("PURCHASE_CREATED", purchaseCreatedCallback);
    toggleView();
    const messages = [
      "Waiting for confirmation of purchase",
      // "If you chose bank transfer you can close the Wizard now.",
      // "Come back when you received the completion E-Mail by Ramp.",
    ];
    addFeedbackMessage(messages);
  };

  const purchaseSuccessfulCallback = (event) => {
    ramp.unsubscribe("PURCHASE_SUCCESSFUL", purchaseSuccessfulCallback);
    addFeedbackMessage([
      "Purchase successful!",
      "Checking balance to get updated",
    ]);

    const boughtAmount = parseInt(event.payload.purchase.cryptoAmount);
    let timeElapsed = 0;
    let timer;
    const checkBalance = async () => {
      if (timeElapsed >= RAMP_BALANCE_TIMEOUT) {
        if (timer) {
          clearInterval(timer);
        }
        addErrorMessage([
          `Balance did not get updated after ${
            RAMP_BALANCE_TIMEOUT / 1000
          } seconds!`,
        ]);
        return;
      }

      const balance = await getBalances(CONFIGURATION_DETAIL_URL);
      if (balance && balance.ETH && balance.ETH.as_wei >= boughtAmount) {
        addFeedbackMessage([
          `Balance got updated. You now have ${balance.ETH.formatted}.`,
        ]);
        setTimeout(() => {
          forceNavigation(SWAP_URL);
        }, 5000);
      }
      timeElapsed += 10000;
    };

    checkBalance();
    timer = setInterval(checkBalance, 10000);
  };

  const purchaseFailedCallback = () => {
    if (!document.querySelector("#background-task-tracker").hidden) {
      addErrorMessage(["Purchase failed! Try again..."]);
    }
  };

  ramp
    .on("PURCHASE_CREATED", purchaseCreatedCallback)
    .on("PURCHASE_SUCCESSFUL", purchaseSuccessfulCallback)
    .on("PURCHASE_FAILED", purchaseFailedCallback)
    .show();
}

async function checkWeb3Network() {
  let required_chain_id = CHAIN_ID;
  await connectWeb3();
  web3.version.getNetwork(function (error, chain_id) {
    if (error) {
      console.error(error);
    }

    if (chain_id != required_chain_id) {
      let current_chain_name = CHAIN_ID_MAPPING[chain_id];
      let required_chain_name = CHAIN_ID_MAPPING[required_chain_id];
      alert(
        `Web3 Browser connected to ${current_chain_name}, please change to ${required_chain_name}.`
      );
    }
  });
}

function makeWeb3Transaction(w3, transaction_data) {
  w3.eth.sendTransaction(transaction_data, function (error, result) {
    if (result) {
      // result is the transaction hash
      trackTransaction(result, CONFIGURATION_FILE_NAME);
    }

    if (error) {
      console.error(error);
    }
  });
}

async function sendEthViaWeb3() {
  await checkWeb3Network();
  let web3 = window.web3;
  let sender_address =
    (window.ethereum && window.ethereum.selectedAddress) ||
    web3.eth.defaultAccount;
  let gasPrice;

  try {
    gasPrice = await getGasPrice(GAS_PRICE_URL);
  } catch {
    console.err("Could not fetch gas price. Falling back to web3 gas price.");
  }

  let transaction_data = {
    from: sender_address,
    to: TARGET_ADDRESS,
    value: neededEthAmount,
  };

  if (gasPrice) {
    transaction_data.gasPrice = gasPrice;
  }

  makeWeb3Transaction(web3, transaction_data);
}

function checkWeb3Available() {
  let has_web3 = Boolean(window.ethereum || window.web3);
  let noWeb3Text = document.getElementById("no-web3");
  if (has_web3) {
    noWeb3Text.style.display = "none";
  } else {
    noWeb3Text.style.display = "inline";
  }
  return has_web3;
}

function updateNeededEth(balance) {
  neededEthAmount = ETHEREUM_REQUIRED_AMOUNT - balance.ETH.as_wei;
  if (balance.ETH.as_wei > 0) {
    const sendButton = document.getElementById("btn-web3-eth");
    sendButton.textContent = "Send missing ETH";
    const info = document.getElementById("low-eth-info");
    if (!info) {
      info = document.createElement("div");
      info.id = "low-eth-info";
      const infoPanel = document.querySelector(".info-panel");
      infoPanel.appendChild(info);
    }
    info.textContent = `You have ${balance.ETH.formatted} but you need ${ETHEREUM_REQUIRED_AMOUNT_FORMATTED}`;
  }
}

function sendEthButtonlogic(balance) {
  const hasWeb3 = checkWeb3Available();
  const hideButtons = hasWeb3 ? hasEnoughEthToStartSwaps(balance) : true;
  const buttonList = document.getElementById("btns-web3");
  if (hideButtons) {
    buttonList.classList.add("hidden");
  } else {
    buttonList.classList.remove("hidden");
  }

  if (!hasWeb3) {
    return;
  }

  if (hasEnoughEthToStartSwaps(balance)) {
    const text = document.createTextNode(
      "Your Raiden account is funded with ETH!"
    );
    const infoPanel = document.querySelector(".info-panel");
    infoPanel.appendChild(text);
    setTimeout(() => {
      forceNavigation(SWAP_URL);
    }, 2000);
  } else {
    updateNeededEth(balance);
  }
}

function showDownloadButton(callback) {
  let keystore_div = document.getElementById("keystore-download");
  keystore_div.classList.add("is-visible");
  let keystore_button = document.getElementById("keystore");
  keystore_button.href = KEYSTORE_URL;
  if (callback) {
    keystore_button.onclick = callback;
  }
}

function removeSpinner() {
  const spinner = document.querySelector(".spinner.balance-loading");
  if (spinner) {
    spinner.remove();
  }
}

async function poll() {
  const balance = await getBalances(CONFIGURATION_DETAIL_URL);
  const config = await getConfigurationFileData(CONFIGURATION_DETAIL_URL);
  removeSpinner();

  if (!balance.ETH.as_wei && config._initial_funding_txhash) {
    return trackTransaction(
      config._initial_funding_txhash,
      CONFIGURATION_FILE_NAME
    );
  }

  if (balance.ETH.as_wei) {
    sendEthButtonlogic(balance);
  } else {
    showDownloadButton(() => {
      sendEthButtonlogic(balance);
    });
  }
}

function main() {
  poll();
}

window.addEventListener("DOMContentLoaded", function () {
  setProgressStep(2, "Fund Account with ETH");
  if (FAUCET_AVAILABLE !== "True") {
    window.MAIN_VIEW_INTERVAL = 10000;
    window.runMainView();
  } else {
    removeSpinner();
    showDownloadButton(() => {
      let button = document.getElementById("btn-funding");
      button.disabled = false;
    });
  }
});
