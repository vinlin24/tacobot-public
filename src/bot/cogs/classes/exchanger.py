"""Implements the Exchanger class."""

import asyncio
import json
import logging
from datetime import datetime
from typing import NoReturn, Optional, Union

import requests

log = logging.getLogger(__name__)

##### EXCHANGER DEFINITION #####


class Exchanger(object):
    """
    Wrapper class for handling interactions with currencyscoop.com and maintaining
    a local json file containing exchange rate data.
    """

    def __init__(self, api_key: str, path: str) -> None:
        """Initialize self with given credentials and json path."""
        self.__api_key = api_key
        self.__path = path
        log.info(f"Initialized Exchanger object with json path set to: {path}")

    ### ATTRIBUTES ###

    @property
    def api_key(self) -> NoReturn:
        raise PermissionError("you cannot view the API key")

    @property
    def path(self) -> str:
        return self.__path

    @property
    def url(self) -> str:
        """Return the URL to make requests to."""
        return f"https://api.currencyscoop.com/v1/latest?api_key={self.__api_key}&format=json"

    @property
    def rates(self) -> Optional[dict[str, float]]:
        """
        Read json data from local json file at self.path and return the table of
        currencies to exchange rates as a Python dict.
        Return None if no data or invalid data found.
        """
        try:
            with open(self.path, "rt") as file:
                data = json.load(file)
                # Delete metadata
                try:
                    del data["LASTUPDATED"]
                except KeyError:
                    pass
                return data
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            return None

    @property
    def last_updated(self) -> Optional[datetime]:
        """
        Return the datetime object representing when local json file was last updated.
        Return None if no data or invalid data found.
        """
        try:
            with open(self.path, "rt") as file:
                data = json.load(file)
                try:
                    last_updated = data["LASTUPDATED"]
                except KeyError:
                    return None
                dt = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S.%f")
                return dt
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            return None

    ##### METHODS #####

    async def update_rates(self, *, loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
        """
        Extract json data from currencyscoop.com and write a table of currencies to
        exchange rates to local json file at self.path. Also save metadata LASTUPDATED
        key that points to the stringified datetime of when extraction occurred.
        Return whether request and update were successful.
        WARNING: Free plan on currencyscoop.com limits usage to 5000 requests/month, which
        is about one request every 10 minutes.
        """
        # Handle default arg
        loop = loop or asyncio.get_event_loop()

        # requests.models.Response
        response = await loop.run_in_executor(None, requests.get, self.url)
        log.warning(
            "Request to currencyscoop.com was attempted. Usage is limited to 5000 requests/mo")

        # Exit as to not overwrite existing data in json file
        if not response.ok:
            log.error(
                f"Response code {response.status_code}: {response.reason}")
            return False

        data = response.json()
        rates_dict = data["response"]["rates"]

        # Add a key to save the datetime of when extraction occurred
        now_str = str(datetime.now())
        rates_dict["LASTUPDATED"] = now_str

        # Update local file
        with open(self.path, "wt") as file:
            json.dump(rates_dict, file, indent=4)

        log.info(f"Updated {self.path} with latest rates")
        return True

    async def convert(self, amount: float, org_currency: str, new_currency: str = "USD", force_update: bool = False, *,
                      loop: Optional[asyncio.AbstractEventLoop] = None) -> Union[float, NoReturn]:
        """
        Return amount in org_currency in terms of new_currency, defaults to USD.
        If no data is found or invalid data found in local json file, manually initialize it
        through update_rates().
        Raise requests.RequestException if update_rates() fails to update rates.
        Raise LookupError if org_currency or new_currency are invalid abbreviations.
        Optional param force_update to specify if program should fetch latest data.
        """
        if force_update or self.rates is None:
            # Update rates; if unsuccessful, exit with exception
            if not await self.update_rates(loop=loop):
                raise requests.RequestException(
                    "unsucessful request in update_rates()")

        try:
            org_rate = self.rates[org_currency]
            new_rate = self.rates[new_currency]
        except KeyError as E:
            raise LookupError(
                f"unrecognized currency abbreviation '{E}'") from None

        return amount * new_rate / org_rate
