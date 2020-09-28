const amountMenus = {};
let selectedExchange = "";
let selectedAmount = 0;

function requestCostEstimation(button, exchange) {
  const estimationElement = document.createElement("div");
  estimationElement.classList.add("estimation");
  const placeholder = document.createTextNode(`Calculating costs...`);
  estimationElement.appendChild(placeholder);
  button.appendChild(estimationElement);

  const data = JSON.stringify({
    exchange: exchange,
    currency: TOKEN_TICKER,
    target_amount: parseInt(button.value) / 10 ** DECIMALS,
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
      button.setAttribute("disabled", true);
    }
  };

  req.open("POST", API_COST_ESTIMATION_ENDPOINT, true);
  req.setRequestHeader("Content-Type", "application/json");
  req.send(data);
}

function addCostsToButtons() {
  const amountButtonsKyber = amountMenus.kyber.querySelectorAll(
    ".amount-button"
  );
  const amountButtonsUniswap = amountMenus.uniswap.querySelectorAll(
    ".amount-button"
  );

  amountButtonsKyber.forEach((button) =>
    requestCostEstimation(button, "kyber")
  );
  amountButtonsUniswap.forEach((button) =>
    requestCostEstimation(button, "uniswap")
  );
}

function setupMenus() {
  const exchangeButtons = document.querySelectorAll(".exchange-button");
  const amountButtons = document.querySelectorAll(".amount-button");

  const validate = () => {
    const submitButton = document.querySelector("button[type=submit]");
    submitButton.disabled = selectedExchange === "" || selectedAmount === 0;
  };

  const selectExchange = (button) => {
    Object.keys(amountMenus).forEach((exchange) => {
      amountMenus[exchange].classList.remove("is-visible");
      const button = amountMenus[exchange]
        .closest(".menu-item")
        .querySelector("button");
      button.classList.remove("selected");
    });
    selectedAmount = 0;
    amountButtons.forEach((button) => button.classList.remove("selected"));

    if (selectedExchange === button.value) {
      selectedExchange = "";
    } else {
      selectedExchange = button.value;
      button.classList.add("selected");
      const newMenuItem = button.closest(".menu-item");
      amountMenus[button.value].classList.add("is-visible");
    }
    validate();
  };

  const selectAmount = (button) => {
    amountButtons.forEach((button) => button.classList.remove("selected"));
    if (selectedAmount === button.value) {
      selectedAmount = 0;
    } else {
      selectedAmount = button.value;
      button.classList.add("selected");
    }
    validate();
  };

  validate();
  exchangeButtons.forEach((button) => {
    button.addEventListener("click", () => selectExchange(button));
  });

  amountButtons.forEach((button) => {
    button.addEventListener("click", () => selectAmount(button));
  });
}

function setupSubmit() {
  const submitButton = document.querySelector("button[type=submit]");

  submitButton.addEventListener("click", function () {
    WEBSOCKET.send(
      JSON.stringify({
        method: "swap",
        configuration_file_name: CONFIGURATION_FILE_NAME,
        amount: selectedAmount.toString(),
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

  amountMenus.kyber = document.querySelector("#amount-menu-kyber");
  amountMenus.uniswap = document.querySelector("#amount-menu-uniswap");

  setupMenus();
  setupSubmit();
  addCostsToButtons();

  window.MAIN_VIEW_INTERVAL = 5000;
  window.runMainView();
});
