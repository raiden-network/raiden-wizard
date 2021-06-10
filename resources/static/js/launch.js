async function main() {
  let balance = await getBalances(CONFIGURATION_DETAIL_URL);

  document.querySelector(".spinner.balance-loading").remove();

  let checklist_elem = document.querySelector("ul.checklist");
  let eth_balance_check_elem = checklist_elem.querySelector(
    "li[data-check=eth-balance]"
  );
  let service_token_balance_check_elem = checklist_elem.querySelector(
    "li[data-check=service-token-balance]"
  );
  let transfer_token_balance_check_elem = checklist_elem.querySelector(
    "li[data-check=transfer-token-balance]"
  );

  let btn_funding = document.getElementById("btn-funding");
  let btn_launch = document.getElementById("btn-launch");

  let eth_balance_display_elem = eth_balance_check_elem.querySelector(
    "span.check-value"
  );
  let service_token_balance_display_elem = service_token_balance_check_elem.querySelector(
    "span.check-value"
  );
  let transfer_token_balance_display_elem = transfer_token_balance_check_elem.querySelector(
    "span.check-value"
  );

  let has_enough_eth = hasEnoughEthToLaunchRaiden(balance);
  let has_enough_service_token = hasEnoughServiceTokenToLaunchRaiden(balance);
  let has_enough_transfer_token = hasEnoughTransferTokenToLaunchRaiden(balance);

  eth_balance_display_elem.textContent = balance.ETH.formatted;
  eth_balance_display_elem.classList.toggle("ok", has_enough_eth);
  eth_balance_display_elem.classList.toggle("nok", !has_enough_eth);

  service_token_balance_display_elem.textContent =
    (balance.service_token && balance.service_token.formatted) || "N/A";
  service_token_balance_display_elem.classList.toggle(
    "ok",
    has_enough_service_token
  );
  service_token_balance_display_elem.classList.toggle(
    "nok",
    !has_enough_service_token
  );

  transfer_token_balance_display_elem.textContent =
    (balance.transfer_token && balance.transfer_token.formatted) || "N/A";
  transfer_token_balance_display_elem.classList.toggle(
    "ok",
    has_enough_transfer_token
  );
  transfer_token_balance_display_elem.classList.toggle(
    "nok",
    !has_enough_transfer_token
  );

  let can_launch =
    has_enough_eth && has_enough_service_token && has_enough_transfer_token;

  btn_funding.disabled = can_launch;
  btn_launch.disabled = !can_launch;
}

window.addEventListener("DOMContentLoaded", async function () {
  setProgressStep(5, "Launch Raiden");
  main();
});
