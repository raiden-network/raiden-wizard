const CHAIN_ID_MAPPING = {
  1: "Mainnet",
  3: "Ropsten",
  4: "Rinkeby",
  5: "Görli",
  42: "Kovan",
};
const RAMP_BALANCE_TIMEOUT = 300000;

let neededEthAmount = ETHEREUM_REQUIRED_AMOUNT;
let provider;

function runFunding(configurationFileName) {
  let message = {
    method: "fund",
    configuration_file_name: configurationFileName,
  };
  WEBSOCKET.send(JSON.stringify(message));
  toggleView();
}

function showRamp() {
  const amountInput = document.getElementById("eth-amount");

  const ramp = new rampInstantSdk.RampInstantSDK({
    hostAppName: "Raiden Wizard",
    hostLogoUrl:
      "https://raw.githubusercontent.com/raiden-network/raiden-wizard/develop/resources/static/images/raiden_logo_black.svg",
    hostApiKey: RAMP_API_KEY,
    swapAmount: toWei(amountInput.value).toString(),
    swapAsset: "ETH",
    userAddress: TARGET_ADDRESS,
  });

  const purchaseCreatedCallback = (event) => {
    console.log(`Ramp purchase created with id ${event.payload.purchase.id}`);
    ramp.unsubscribe('PURCHASE_CREATED', purchaseCreatedCallback);
    toggleView();
    const messages = [
      "Waiting for confirmation of purchase",
      "(If you chose manual bank transfer you can close the Wizard and come back once you received a confirmation by e-mail.)",
    ];
    addFeedbackMessage(messages);
  };

  const purchaseSuccessfulCallback = (event) => {
    ramp.unsubscribe("PURCHASE_SUCCESSFUL", purchaseSuccessfulCallback);
    addFeedbackMessage([
      'Purchase successful!',
      'Checking balance to get updated',
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
  let currentChainID;
  try {
    currentChainID = parseInt(await provider.request({ method: 'eth_chainId' }), 16);
  } catch (error) {
    alert('Could not retrieve the chaind id from the web3 provider.');
    return false;
  }

  const requiredChainID = CHAIN_ID;
  if (currentChainID != requiredChainID) {
    const currentChainName = CHAIN_ID_MAPPING[currentChainID];
    const requiredChainName = CHAIN_ID_MAPPING[requiredChainID];
    alert(
      `Web3 Browser connected to ${currentChainName}, please change to ${requiredChainName}.`
    );
    return false;
  }
  return true;
}

async function connectWeb3() {
  let accounts = [];
  try {
    accounts = await provider.request({ method: 'eth_requestAccounts' });
  } catch (error) {
    if (error.code === 4001) {
      // EIP-1193 userRejectedRequest error
      alert('Permissions to the web3 provider\'s accounts needed in order to continue.');
    } else {
      alert('Not able to connect to the web3 provider.');
      console.error(error);
    }
  }
  return accounts;
}

async function makeWeb3Transaction(transactionParams) {
  let transactionHash;
  try {
    transactionHash = await provider.request({ method: 'eth_sendTransaction', params: [transactionParams]});
  } catch (error) {
    console.error(error);
  }
  if (transactionHash) {
    trackTransaction(transactionHash, CONFIGURATION_FILE_NAME);
  }
}

async function sendEthViaWeb3() {
  const correctNetwork = await checkWeb3Network();
  if (!correctNetwork) {
    return;
  }

  const accounts = await connectWeb3();
  if (accounts.length === 0) {
    return;
  }

  let gasPrice;
  try {
    gasPrice = await getGasPrice(GAS_PRICE_URL);
  } catch {
    console.err('Could not fetch gas price. Falling back to web3 gas price.');
  }

  const amountInput = document.getElementById("eth-amount");
  const transactionParams = {
    from: accounts[0],
    to: TARGET_ADDRESS,
    value: '0x' + toWei(amountInput.value).toString(16),
  };

  if (gasPrice) {
    transactionParams.gasPrice = '0x' + gasPrice.toString(16);
  }

  makeWeb3Transaction(transactionParams);
}

function checkWeb3Available() {
  let hasWeb3 = provider && provider.request;
  let noWeb3Text = document.getElementById("no-web3");
  if (hasWeb3) {
    noWeb3Text.style.display = "none";
  } else {
    noWeb3Text.style.display = "inline";
  }
  return hasWeb3;
}

function checkEthAmountValidity(event) {
  const amountInput = event.target;
  const errorDisplay = document.querySelector('span.error');
  const sendButton = document.getElementById('btn-web3-eth');
  const rampButton = document.getElementById('btn-ramp-eth');

  if (
    amountInput.validity.valueMissing || 
    amountInput.validity.rangeUnderflow || 
    amountInput.validity.badInput 
  ) {
    errorDisplay.textContent = `At least ${fromWei(neededEthAmount)} ETH required`;
    errorDisplay.hidden = false;
    sendButton.disabled = true;
    rampButton.disabled = true;
  } else {
    errorDisplay.hidden = true;
    sendButton.disabled = false;
    rampButton.disabled = false;
  }
}

function setUpEthAmountCheck() {
  const amountInput = document.getElementById("eth-amount");
  amountInput.addEventListener("input", checkEthAmountValidity);
}

function updateNeededEth(balance) {
  neededEthAmount = ETHEREUM_REQUIRED_AMOUNT - balance.ETH.as_wei;
  if (balance.ETH.as_wei > 0) {
    const amountInput = document.getElementById("eth-amount");
    amountInput.min = fromWei(neededEthAmount);
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

window.addEventListener("DOMContentLoaded", async function () {
  setProgressStep(2, "Fund Account with ETH");
  if (FAUCET_AVAILABLE !== "True") {
    provider = await detectEthereumProvider();
    setUpEthAmountCheck();
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
