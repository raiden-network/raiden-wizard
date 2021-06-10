const CHAIN_ID_MAPPING = {
  1: "Mainnet",
  3: "Ropsten",
  4: "Rinkeby",
  5: "Görli",
  42: "Kovan",
};

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

  const transactionParams = {
    from: accounts[0],
    to: TARGET_ADDRESS,
    value: '0x' + neededEthAmount.toString(16),
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

window.addEventListener("DOMContentLoaded", async function () {
  setProgressStep(2, "Fund Account with ETH");
  if (FAUCET_AVAILABLE !== "True") {
    provider = await detectEthereumProvider();
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
