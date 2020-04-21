import copy

import raiden_installer


def override_settings(**attrs):
    def decorator(fn):
        def wrapper(*args, **kw):
            original_settings = copy.copy(raiden_installer.default_settings)
            for attr, value in attrs.items():
                raiden_installer.default_settings.__dict__[attr] = value
            result = fn(*args, **kw)
            raiden_installer.default_settings = original_settings
            return result

        return wrapper

    return decorator
