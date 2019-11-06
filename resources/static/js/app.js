const newConfigurationButton = document.getElementsByClassName('new-configuration-button');
const setupError = document.getElementsByClassName('setup-error');


enableButton = (e) => {
  if (e.target.id == 'endpoint') {
    newConfigurationButton[0].disabled = false;
    setupError[0].style.visibility = 'hidden';
  }
}

inputValidation = (e) => {
  const regEx = /^[a-fA-F0-9]+$/;

  if (e.target.id == 'endpoint' && !e.target.value.match(regEx)) {
    newConfigurationButton[0].disabled = true;
    setupError[0].style.visibility = 'visible';
  }
}