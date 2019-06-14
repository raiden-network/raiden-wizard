class PlainTxtPwd:
    '''
    Provides a method for storing the keystore pwd in a plain txt
    file which is necessary when initializing Raiden and a method
    for deleting that very same file.

    Intended for testnet use only with throwaway keystore account
    and pwd.
    '''
    def __init__(self, dest_dir: str, keystore_pwd: str):
        pass

    def create_plain_txt_pwd_file(self):
        pass

    def delete_plain_txt_pwd_file(self):
        pass