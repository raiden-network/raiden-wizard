window.addEventListener("load", function () {
  setProgressStep(1, "Connect to the Ethereum Blockchain");

  const infura_project_input = document.querySelector("input[name=endpoint]");
  const error_display = document.querySelector("span.error");
  const submit_button = document.querySelector("button");

  function checkIdNotEmpty(evt) {
    const error_message = "Please enter your Infura ID.";

    if (!evt.target.value) {
      error_display.textContent = error_message;
      error_display.hidden = false;
      submit_button.disabled = true;
    } else {
      error_display.hidden = true;
      submit_button.disabled = false;
    }
  }

  function submitConfiguration(evt) {
    WEBSOCKET.send(
      JSON.stringify({
        method: "setup",
        endpoint: infura_project_input.value,
        network: NETWORK_NAME,
        account_file: ACCOUNT_FILE,
      })
    );

    toggleView();
  }

  // Attaching event handlers
  infura_project_input.addEventListener("input", checkIdNotEmpty);
  submit_button.addEventListener("click", submitConfiguration);
});
