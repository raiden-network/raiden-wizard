window.addEventListener("DOMContentLoaded", function () {
  const passphrase = document.querySelector("input[name=passphrase]");
  const submit_button = document.querySelector("button");

  function submitPassphrase(evt) {
    WEBSOCKET.send(
      JSON.stringify({
        method: "unlock",
        passphrase: passphrase.value,
        keystore_file_path: KEYSTORE_FILE_PATH,
        return_to: RETURN_TO,
      })
    );

    toggleView();
  }

  submit_button.addEventListener("click", submitPassphrase);
});
