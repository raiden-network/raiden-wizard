from pathlib import Path


def list_requirements(req_file: str) -> list:
    '''
    Get all dependency names and versions from
    requirements.txt and append them to a list.
    '''
    req_file = Path(req_file)
    req_list = []

    try:
        with open(req_file, 'r') as requirements:
            for requirement in requirements:
                requirement = requirement.strip()
                req_list.append(requirement)

        return req_list
    except OSError as err:
        print('Not a valid requirements file')
