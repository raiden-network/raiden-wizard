inputToggle = (inputField) => {
    const ethRpc = document.getElementById('eth-rpc')
    const keystore = document.getElementById('keystore')

    if (inputField == 'eth-rpc') {
        keystore.style.display = 'none'
        ethRpc.style.display = 'grid'
    } else if (inputField == 'keystore') {
        ethRpc.style.display = 'none'
        keystore.style.display = 'grid'
    }
}