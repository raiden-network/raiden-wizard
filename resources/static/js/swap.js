let selectedExchange = "";

function validate() {
  const submitButton = document.querySelector("button[type=submit]");
  submitButton.disabled = selectedExchange === "";
}

function requestCostEstimation(button) {
  const estimationElement = document.createElement("div");
  estimationElement.classList.add("estimation");
  const placeholder = document.createTextNode(`Calculating costs...`);
  estimationElement.appendChild(placeholder);
  button.appendChild(estimationElement);

  const data = JSON.stringify({
    exchange: button.value,
    currency: TOKEN_TICKER,
    target_amount: SWAP_AMOUNT / 10 ** DECIMALS,
  });

  const req = new XMLHttpRequest();

  req.onload = function () {
    if (this.status == 200) {
      const res = JSON.parse(this.response);
      const text = document.createTextNode(
        `Approximately ${res.formatted} as per exchange`
      );
      placeholder.remove();
      estimationElement.appendChild(text);
    } else {
      const error = document.createTextNode(`Swap not possible at the moment.`);
      placeholder.remove();
      estimationElement.appendChild(error);

      button.disabled = true;
      if (selectedExchange === button.value) {
        selectedExchange = "";
      }
      validate();
    }
  };

  req.open("POST", API_COST_ESTIMATION_ENDPOINT, true);
  req.setRequestHeader("Content-Type", "application/json");
  req.send(data);
}

function addCostsToButtons() {
  const exchangeButtons = document.querySelectorAll(".exchange-button");

  exchangeButtons.forEach((button) => requestCostEstimation(button, "kyber"));
}

function setupButtons() {
  const exchangeButtons = document.querySelectorAll(".exchange-button");

  const selectExchange = (button) => {
    exchangeButtons.forEach((element) => element.classList.remove("selected"));

    if (selectedExchange === button.value) {
      selectedExchange = "";
    } else {
      selectedExchange = button.value;
      button.classList.add("selected");
    }
    validate();
  };

  validate();
  exchangeButtons.forEach((button) => {
    button.addEventListener("click", () => selectExchange(button));
  });
}

function setupSubmit() {
  const submitButton = document.querySelector("button[type=submit]");

  submitButton.addEventListener("click", function () {
    WEBSOCKET.send(
      JSON.stringify({
        method: "swap",
        configuration_file_name: CONFIGURATION_FILE_NAME,
        amount: SWAP_AMOUNT.toString(),
        token: TOKEN_TICKER,
        exchange: selectedExchange,
      })
    );

    toggleView();
  });
}

async function skipSwap() {
  let balance = await getBalances(CONFIGURATION_DETAIL_URL);

  if (TOKEN_TICKER === "RDN" && hasEnoughServiceTokenToLaunchRaiden(balance)) {
    toggleView();
    WEBSOCKET.send(
      JSON.stringify({
        method: "udc_deposit",
        configuration_file_name: CONFIGURATION_FILE_NAME,
      })
    );
  } else if (
    TOKEN_TICKER === "DAI" &&
    hasEnoughTransferTokenToLaunchRaiden(balance)
  ) {
    document.querySelector(
      ".hero"
    ).innerHTML = `Funds of ${balance.transfer_token.formatted} already acquired <br/>
      Moving on to launch Raiden`;
    setTimeout(function () {
      forceNavigation(LAUNCH_URL);
    }, 5000);
  }
}

function main() {
  skipSwap();
}

window.addEventListener("DOMContentLoaded", function () {
  if (TOKEN_TICKER === "RDN") {
    setProgressStep(3, "Fund Account with RDN");
  } else if (TOKEN_TICKER === "DAI") {
    setProgressStep(4, "Fund Account with DAI");
  }

  setupButtons();
  setupSubmit();
  addCostsToButtons();

  window.MAIN_VIEW_INTERVAL = 5000;
  window.runMainView();
});
