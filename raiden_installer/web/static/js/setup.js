window.onload = function() {
    const API_CONFIGURATION_LIST_ENDPOINT = "/api/configurations";
    const infura_project_input = document.querySelector("input");
    const error_display = document.querySelector("span.error");
    const submit_button = document.querySelector("button");

    const configuration_launcher_section = document.getElementById("configuration-launcher");
    const configuration_list_container = document.querySelector("ul.available-configurations");


    function validateInfuraId(evt) {
        const infura_id = evt.target.value;
        const error_message = "Infura IDs must be exactly 32 characters long";

        if (!infura_id || infura_id.length != 32) {
            error_display.textContent = error_message;
            error_display.hidden = false;
            submit_button.disabled = true;

        }
        else {
            error_display.hidden = true;
            submit_button.disabled = false;
        }
    }

    function submitConfiguration(evt) {
        const data = JSON.stringify({
            endpoint: infura_project_input.value
        });

        const req = new XMLHttpRequest();

        req.onload = function() {
            if (this.status == 201) {
                const new_config_url = this.getResponseHeader("Location");
                const config_req = new XMLHttpRequest();

                config_req.onload = function() {
                    if (this.status == 200){
                        let config_data = JSON.parse(this.response);
                        document.location = config_data.account_page_url;
                    }
                };
                config_req.open("GET", new_config_url);
                config_req.send();
            }
        }

        req.open("POST", API_CONFIGURATION_LIST_ENDPOINT, true);
        req.setRequestHeader("Content-Type", "application/json");
        req.send(data);
    }



    function addConfiguration(configuration_data) {
        // Function that loads existing configuration asynchronously,
        // To avoid taking too-long to load all configurations before rendering anything.
        const configuration_item_container = document.createElement("li");
        const account_element = document.createElement("span");
        const network_element = document.createElement("span");
        const balance_element = document.createElement("span");
        const launch_button = document.createElement("a");

        account_element.classList.add("account");
        network_element.classList.add("network");
        balance_element.classList.add("balance");
        launch_button.classList.add("button");

        account_element.textContent = configuration_data.account;
        network_element.textContent = configuration_data.network;
        balance_element.textContent = "Balance: " + configuration_data.balance.formatted;
        launch_button.textContent = "Launch";
        launch_button.setAttribute("href", configuration_data.launch_page_url);

        configuration_item_container.appendChild(account_element);
        configuration_item_container.appendChild(network_element);
        configuration_item_container.appendChild(balance_element);
        configuration_item_container.appendChild(launch_button);

        configuration_list_container.appendChild(configuration_item_container);

        configuration_launcher_section.hidden = false;
    }

    function getExistingConfigurations() {
        const req = new XMLHttpRequest();
        req.open("GET", API_CONFIGURATION_LIST_ENDPOINT, true);

        req.onload = function() {
            if (this.status == 200) {
                const urls = JSON.parse(this.response);
                urls.forEach(function(conf_url) {
                    var conf_req = new XMLHttpRequest();
                    conf_req.open("GET", conf_url, true);
                    conf_req.onload = function() {
                        if (this.status == 200) {
                            addConfiguration(JSON.parse(this.response));
                        }
                    }
                    conf_req.send();
                });
            }
        }

        req.send();
    }

    // Attaching event handlers
    infura_project_input.addEventListener("blur", validateInfuraId);
    infura_project_input.addEventListener("change", validateInfuraId);
    submit_button.addEventListener("click", submitConfiguration);


    // Load configurations
    getExistingConfigurations();
}
