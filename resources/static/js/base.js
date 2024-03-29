var MAIN_VIEW_INTERVAL;
var RUNNING_TIMERS = new Array();

let video;

function runMainView() {
  if (typeof window.main === "function") {
    main();

    if (MAIN_VIEW_INTERVAL) {
      RUNNING_TIMERS.push(setInterval(window.main, MAIN_VIEW_INTERVAL));
    }
  }
}

function stopMainView() {
  while (RUNNING_TIMERS.length) {
    let timer = RUNNING_TIMERS.pop();
    clearInterval(timer);
  }
}

async function getSwapEstimatedCosts(api_cost_estimation_url) {
  let request = await fetch(api_cost_estimation_url);
  let response_data = await request.json();
  return response_data;
}

async function getGasPrice(api_gas_price) {
  let request = await fetch(api_gas_price);
  let response_data = await request.json();
  return response_data["gas_price"];
}

function showLaunchVideo(loadedCallback) {
  if (video) {
    video.remove();
  }

  video = document.createElement("video");
  if (!video.canPlayType("video/mp4")) {
    video = undefined;
    loadedCallback();
    return;
  }

  const videoWrapper = document.querySelector(".video-wrapper");
  const tracker = document.querySelector("#background-task-tracker");

  video.autoplay = "true";
  video.playsinline = "true";
  video.muted = "true";
  video.type = "video/mp4";
  video.addEventListener("ended", () => {
    video.remove();
    videoWrapper.classList.remove("is-visible");
    tracker.classList.remove("video-tracker");
    video = undefined;
  });

  const req = new XMLHttpRequest();
  req.open("GET", LAUNCH_VIDEO_URL, true);
  req.responseType = "blob";

  req.onload = function () {
    if (this.status === 200) {
      var videoBlob = this.response;
      var videoSrc = URL.createObjectURL(videoBlob);
      video.src = videoSrc;
      videoWrapper.classList.add("is-visible");
      videoWrapper.appendChild(video);
      tracker.classList.add("video-tracker");
      loadedCallback();
    }
  };
  req.onerror = function () {
    video = undefined;
    loadedCallback();
  };
  req.send();
}

function launchRaiden(configuration_file_name) {
  const onVideoLoaded = () => {
    let message = {
      method: "launch",
      configuration_file_name: configuration_file_name,
    };
    WEBSOCKET.send(JSON.stringify(message));
    toggleView();
  };
  showLaunchVideo(onVideoLoaded);
}

function hasEnoughEthToStartSwaps(balance) {
  return (
    balance && balance.ETH && balance.ETH.as_wei >= ETHEREUM_REQUIRED_AMOUNT
  );
}

function hasEnoughEthToLaunchRaiden(balance) {
  return (
    balance &&
    balance.ETH &&
    balance.ETH.as_wei >= ETHEREUM_REQUIRED_AMOUNT_AFTER_SWAP
  );
}

function hasEnoughServiceTokenToLaunchRaiden(balance) {
  return (
    balance &&
    balance.service_token &&
    balance.service_token.as_wei >= 0.9 * SERVICE_TOKEN_REQUIRED_AMOUNT
  );
}

function hasEnoughTransferTokenToLaunchRaiden(balance) {
  return (
    balance &&
    balance.transfer_token &&
    balance.transfer_token.as_wei >= 0.9 * TRANSFER_TOKEN_REQUIRED_AMOUNT
  );
}

function hasEnoughBalanceToLaunchRaiden(balance) {
  let enough_token =
    hasEnoughServiceTokenToLaunchRaiden(balance) &&
    hasEnoughTransferTokenToLaunchRaiden(balance);
  let enough_eth = hasEnoughEthToLaunchRaiden(balance);
  return enough_token && enough_eth;
}

function trackTransaction(tx_hash, configuration_file_name) {
  let message = {
    method: "track_transaction",
    configuration_file_name: configuration_file_name,
    tx_hash: tx_hash,
  };
  WEBSOCKET.send(JSON.stringify(message));
  toggleView();
}

function resetSpinner() {
  let spinner_elem = document.querySelector(
    "#background-task-tracker div.task-status-icon"
  );

  spinner_elem.classList.remove("complete");
  spinner_elem.classList.add("spinner");
}

function copyToClipboard(container_element, content_element) {
  container_element.classList.add("clipboard");
  navigator.clipboard.writeText(content_element.textContent.trim());
  setTimeout(function () {
    container_element.classList.remove("clipboard");
  }, 1000);
}

function toggleView() {
  let container = document.querySelector("section > div.container");
  let tracker_elem = document.querySelector("#background-task-tracker");

  let message_list = tracker_elem.querySelector("ul.messages");

  if (tracker_elem.hidden) {
    stopMainView();
    container.classList.add("hidden");

    resetSpinner();
    while (message_list.firstChild) {
      message_list.removeChild(message_list.firstChild);
    }
    tracker_elem.hidden = false;
  } else {
    runMainView();
    container.classList.remove("hidden");
    tracker_elem.hidden = true;
  }
}

async function getConfigurationFileData(configuration_file_url) {
  let request = await fetch(configuration_file_url);
  return await request.json();
}

async function getBalances(configuration_file_url) {
  let configuration_file_data = await getConfigurationFileData(
    configuration_file_url
  );
  return configuration_file_data && configuration_file_data.balance;
}

function updateBalanceDisplay(balance, opts) {
  let eth_balance_display = opts.ethereum_element;
  let service_token_display = opts.service_token_element;
  let transfer_token_display = opts.transfer_token_element;

  if (balance && balance.ETH && eth_balance_display) {
    eth_balance_display.textContent = balance && balance.ETH.formatted;
  }

  if (balance && balance.service_token && service_token_display) {
    service_token_display.textContent =
      balance && balance.service_token.formatted;
  }

  if (balance && balance.transfer_token && transfer_token_display) {
    transfer_token_display.textContent =
      balance && balance.transfer_token.formatted;
  }
}

function checkAcknowledgements(check_input_elems, next_action_elem, callback) {
  check_input_elems.forEach(function (checkbox) {
    checkbox.addEventListener("click", function (evt) {
      let all_checked = true;

      for (let elem of check_input_elems) {
        if (!elem.checked) {
          all_checked = false;
        }
      }

      next_action_elem.disabled = !all_checked;

      if (all_checked && callback) {
        callback();
      }
    });
  });
}

function fromWei(value) {
  return value / 10 ** 18;
}

function toWei(value) {
  return value * 10 ** 18;
}

WEBSOCKET.onmessage = function (evt) {
  let message = JSON.parse(evt.data);
  let message_list_elem = document.querySelector(
    "#background-task-tracker ul.messages"
  );
  let spinner_elem = document.querySelector(
    "#background-task-tracker div.task-status-icon"
  );
  let next_view = null;
  let li = document.createElement("li");
  let waiting_time = 2000;

  resetSpinner();

  switch (message.type) {
    case "error-message":
      li.classList.add("error");
      next_view = toggleView;
      waiting_time = 5000;
      break;
    case "task-complete":
      spinner_elem.classList.remove("spinner");
      spinner_elem.classList.add("complete");
      next_view = toggleView;
      break;
    case "next-step":
      setProgressStep(message.step, message.title);
      break;
    case "redirect":
      next_view = function () {
        forceNavigation(message.redirect_url);
      };
    case "summary":
      spinner_elem.classList.remove("spinner");
      while (message_list_elem.firstChild) {
        message_list_elem.removeChild(message_list_elem.firstChild);
      }
      message_list_elem.classList.add("big");
      if (message.icon) {
        let img = document.createElement("img");
        img.src = ICON_URLS[message.icon];
        message_list_elem.appendChild(img);
      }
      break;
  }

  if (message.text) {
    console.log(message);
    console.log(message.text);
    message.text.forEach((element) => {
      let li = document.createElement("li");
      li.textContent = element;
      message_list_elem.appendChild(li);
    });
  }

  if (message.tx_hash) {
    let li = document.createElement("li");
    let link_text = `${message.tx_hash.substring(
      0,
      6
    )}....${message.tx_hash.substring(message.tx_hash.length - 4)}`;
    li.innerHTML = `<a href="https://etherscan.io/tx/${message.tx_hash}" target="_blank">${link_text}</a>`;
    message_list_elem.appendChild(li);
  }

  if (next_view) {
    setTimeout(next_view, waiting_time);
  }
};

function addFeedbackMessage(message) {
  WEBSOCKET.onmessage({ data: JSON.stringify({ text: message }) });
}

function addErrorMessage(message) {
  WEBSOCKET.onmessage({
    data: JSON.stringify({ text: message, type: "error-message" }),
  });
}

function setupModal() {
  const modalTriggers = document.querySelectorAll(".modal-trigger");
  const bodyBlackout = document.querySelector(".body-blackout");

  modalTriggers.forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const { modalTrigger } = trigger.dataset;
      const modal = document.querySelector(`[data-modal="${modalTrigger}"]`);

      modal.classList.add("is-visible");
      bodyBlackout.classList.add("is-blacked-out");

      modal.querySelector(".modal__close").addEventListener("click", () => {
        modal.classList.remove("is-visible");
        bodyBlackout.classList.remove("is-blacked-out");
      });

      bodyBlackout.addEventListener("click", () => {
        modal.classList.remove("is-visible");
        bodyBlackout.classList.remove("is-blacked-out");
      });
    });
  });
}

function setupTooltips() {
  const tooltipItems = document.querySelectorAll(".tooltip-item");

  tooltipItems.forEach((item) => {
    const tooltip = item.querySelector(".tooltip");

    document.addEventListener("click", (event) => {
      const target = event.target;

      if (item.contains(target)) {
        tooltip.classList.add("is-visible");
      } else {
        tooltip.classList.remove("is-visible");
      }
    });
  });
}

function setProgressStep(step, title) {
  const progressContainer = document.querySelector(".progress");
  progressContainer.classList.add("is-visible");
  const titleText = document.createTextNode(title);
  const headline = progressContainer.querySelector("h2");
  while (headline.firstChild) {
    headline.firstChild.remove();
  }
  headline.appendChild(titleText);
  const progressItems = progressContainer.querySelectorAll(".circle");
  progressItems.forEach((item) => item.classList.remove("active"));
  progressItems[step].classList.add("active");
}

function beforeunloadHandler(e) {
  e.preventDefault();
  e.returnValue = "";
}

function forceNavigation(url) {
  removeBeforeunloadHandler();
  document.location = url;
}

function removeBeforeunloadHandler() {
  window.removeEventListener("beforeunload", beforeunloadHandler);
}

function setUpTogglePassword() {
  const eye = document.getElementById("eye");
  if (!eye) {
    return;
  }
  const passphrase =
    document.querySelector("input[name=passphrase]") ||
    document.querySelector("input[name=passphrase1]");
  function togglePassword(evt) {
    if (passphrase.type === "password") {
      passphrase.type = "text";
      eye.src = EYE_OPEN_URL;
    } else {
      passphrase.type = "password";
      eye.src = EYE_CLOSED_URL;
    }
  }
  eye.addEventListener("click", togglePassword);
}

window.addEventListener("beforeunload", beforeunloadHandler);

window.addEventListener("DOMContentLoaded", function () {
  let link_buttons = document.querySelectorAll("button.link-button");

  link_buttons.forEach(function (elem) {
    elem.addEventListener("click", function (evt) {
      forceNavigation(elem.getAttribute("data-link-url"));
    });
  });

  setupModal();
  setupTooltips();
  setUpTogglePassword();
});
