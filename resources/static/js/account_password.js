window.addEventListener("DOMContentLoaded", function () {
  setProgressStep(0, "Create a Raiden Account");

  const passphrase1 = document.querySelector("input[name=passphrase1]");
  const passphrase2 = document.querySelector("input[name=passphrase2]");
  const error_display = document.querySelector("span.error");
  const submit_button = document.querySelector("button");

  function checkPassphraseMatch(evt) {
    const error_message = "Passwords not matching";
    valid = false;

    if (evt.target.value) {
      if (passphrase1.value == passphrase2.value) {
        valid = true;
      }
    }
    if (valid) {
      error_display.hidden = true;
      submit_button.disabled = false;
    } else {
      error_display.textContent = error_message;
      error_display.hidden = false;
      submit_button.disabled = true;
    }
  }

  function submitPassphrase(evt) {
    WEBSOCKET.send(
      JSON.stringify({
        method: "create_wallet",
        passphrase1: passphrase1.value,
        passphrase2: passphrase2.value,
      })
    );

    toggleView();
  }

  // Attaching event handlers
  passphrase1.addEventListener("input", checkPassphraseMatch);
  passphrase2.addEventListener("input", checkPassphraseMatch);
  submit_button.addEventListener("click", submitPassphrase);
});
