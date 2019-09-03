from typing import TypeVar, Type, List

from urllib.parse import urljoin
import requests


T = TypeVar("T", bound="BaseResource")


class BaseResource:
    ROOT_ENDPOINT = "https://api.kyber.network"
    RESOURCE_PATH = None

    def __init__(self, **kw) -> None:
        for key, value in kw.items():
            setattr(self, key, value)

    @classmethod
    def load(cls: Type[T]) -> List[T]:
        if not cls.RESOURCE_PATH:
            raise NotImplementedError("Resource does not have an endpoint defined")

        response = requests.get(urljoin(cls.ROOT_ENDPOINT, cls.RESOURCE_PATH))
        response.raise_for_status()
        resources = response.json().get("data", [])
        return [cls(**resource_data) for resource_data in resources]
