enableButtons = e => {
  const toEthRpcButton = document.getElementById("to-eth-rpc");
  const toInstallationButton = document.getElementById("to-installation");

  const pwdError = document.querySelector(".pwd-error p");
  const projIdError = document.querySelector(".proj-id-error p");

  if (e.target.name == "keystore-pwd") {
    toEthRpcButton.disabled = false;
    pwdError.style.visibility = "hidden";
  }
  if (e.target.name == "proj-id") {
    toInstallationButton.disabled = false;
    projIdError.style.visibility = "hidden";
  }
};

inputValidation = e => {
  const toEthRpcButton = document.getElementById("to-eth-rpc");
  const toInstallationButton = document.getElementById("to-installation");

  const pwdError = document.querySelector(".pwd-error p");
  const projIdError = document.querySelector(".proj-id-error p");

  // Check whether the project ID matches a hexadecimal string
  const regEx = /^[a-fA-F0-9]+$/;

  if (e.target.name == "keystore-pwd" && e.target.value <= 0) {
    // toEthRpcButton.disabled = true;
    // pwdError.style.visibility = "visible";
  }
  if (e.target.name == "proj-id" && !e.target.value.match(regEx)) {
    // toInstallationButton.disabled = true;
    // projIdError.style.visibility = "visible";
  }
};

inputToggle = installerWindow => {
  const keystoreWindow = document.getElementById("keystore");
  const ethRpcWindow = document.getElementById("eth-rpc");
  const installationWindow = document.getElementById("installation");

  if (installerWindow == "eth-rpc") {
    keystoreWindow.style.display = "none";
    ethRpcWindow.style.display = "grid";
  }
  if (installerWindow == "keystore") {
    keystoreWindow.style.display = "grid";
    ethRpcWindow.style.display = "none";
  }
  if (installerWindow == "installation") {
    ethRpcWindow.style.display = "none";
    installationWindow.style.display = "grid";
  }
};
