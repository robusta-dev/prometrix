from datetime import datetime
from typing import Dict, Optional, List

import requests
from prometheus_api_client import (PrometheusApiClientException,
                                   PrometheusConnect)
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, HTTPError

from prometrix.auth import PrometheusAuthorization
from prometrix.exceptions import (PrometheusFlagsConnectionError,
                                  PrometheusNotFound, VictoriaMetricsNotFound)
from prometrix.models.prometheus_config import PrometheusApis, PrometheusConfig


class CustomPrometheusConnect(PrometheusConnect):
    def __init__(self, config: PrometheusConfig):
        super().__init__(
            url=config.url, disable_ssl=config.disable_ssl, headers=config.headers
        )
        self.config = config
        self._session = requests.Session()
        self._session.mount(self.url, HTTPAdapter(pool_maxsize=10, pool_block=True))

    def safe_custom_query_range(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        step: str,
        params: dict = None,
    ):
        """
        The main difference here is that the method here is POST and the prometheus_cli is GET
        """
        start = round(start_time.timestamp())
        end = round(end_time.timestamp())
        params = params or {}
        data = None
        query = str(query)
        # using the query_range API to get raw data
        response = self._session.post(
            "{0}/api/v1/query_range".format(self.url),
            data={
                "query": query,
                "start": start,
                "end": end,
                "step": step,
                **params,
            },
            verify=self.ssl_verification,
            headers=self.headers,
        )
        if response.status_code == 200:
            return response.json()["data"]
        else:
            raise PrometheusApiClientException(
                "HTTP Status Code {} ({!r})".format(
                    response.status_code, response.content
                )
            )

    def _custom_query(self, query: str, params: dict = None):
        """
        The main difference here is that the method here is POST and the prometheus_cli is GET
        """
        params = params or {}
        data = None
        query = str(query)
        # using the query API to get raw data
        response = self._session.post(
            "{0}/api/v1/query".format(self.url),
            data={"query": query, **params},
            verify=self.ssl_verification,
            headers=self.headers,
        )
        return response

    def get_label_values(self, label_name: str, params: dict = None):
        if PrometheusApis.LABELS not in self.config.supported_apis:
            raise PrometheusApiClientException("Labels Api not supported")
        return super().get_label_values(label_name, params)

    def safe_custom_query(self, query: str, params: dict = None):
        response = self._custom_query(query, params)
        if response.status_code == 200:
            data = response.json()["data"]
        else:
            raise PrometheusApiClientException(
                "HTTP Status Code {} ({!r})".format(
                    response.status_code, response.content
                )
            )
        return data

    def check_prometheus_connection(self, params: dict = None):
        params = params or {}
        try:
            response = self._custom_query(query="example", params=params)
            if response.status_code == 401:
                if PrometheusAuthorization.request_new_token(self.config):
                    self.headers = PrometheusAuthorization.get_authorization_headers(
                        self.config
                    )
                    response = self._custom_query(query="example", params=params)
            response.raise_for_status()
        except (ConnectionError, HTTPError, PrometheusApiClientException) as e:
            raise PrometheusNotFound(
                f"Couldn't connect to Prometheus found under {self.url}\nCaused by {e.__class__.__name__}: {e})"
            ) from e

    def __text_config_to_dict(self, text: str) -> Dict:
        conf = {}
        lines = text.strip().split("\n")
        for line in lines:
            key, val = line.strip().split("=")
            conf[key] = val.strip('"')

        return conf

    def get_prometheus_flags(self) -> Optional[Dict]:
        try:
            if PrometheusApis.FLAGS in self.config.supported_apis:
                return self.fetch_prometheus_flags()
            if PrometheusApis.VM_FLAGS in self.config.supported_apis:
                return self.fetch_victoria_metrics_flags()
        except Exception as e:
            service_name = (
                "Prometheus"
                if PrometheusApis.FLAGS in self.config.supported_apis
                else "Victoria Metrics"
            )
            raise PrometheusFlagsConnectionError(
                f"Couldn't connect to the url: {self.url}\n\t\t{service_name}: {e}"
            )

    def fetch_prometheus_flags(self) -> Dict:
        try:
            response = self._session.get(
                f"{self.url}/api/v1/status/flags",
                verify=self.ssl_verification,
                headers=self.headers,
                # This query should return empty results, but is correct
                params={},
            )
            response.raise_for_status()
            return response.json().get("data", {})
        except Exception as e:
            raise PrometheusNotFound(
                f"Couldn't connect to Prometheus found under {self.url}\nCaused by {e.__class__.__name__}: {e})"
            ) from e

    def fetch_victoria_metrics_flags(self) -> Dict:
        try:
            # connecting to VictoriaMetrics
            response = self._session.get(
                f"{self.url}/flags",
                verify=self.ssl_verification,
                headers=self.headers,
                # This query should return empty results, but is correct
                params={},
            )
            response.raise_for_status()

            configuration = self.__text_config_to_dict(response.text)
            return configuration
        except Exception as e:
            raise VictoriaMetricsNotFound(
                f"Couldn't connect to VictoriaMetrics found under {self.url}\nCaused by {e.__class__.__name__}: {e})"
            ) from e

    def _send_series(self, data: dict, params: dict) -> requests.Response:
        return self._session.post(
            f"{self.url}/api/v1/series",
            data=data,
            verify=self.ssl_verification,
            headers=self.headers,
            params=params,
        )

    def get_series(self, match: List[str], start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None, params: dict = None) -> Dict:
        """
        Retrieves a dictionary of series that match the specified label sets from Prometheus.

        :param match: (List[str]) List of string selectors to specify the series to match.
        :param start_time: (Optional[datetime]) The start time for the query as a datetime object.
        :param end_time: (Optional[datetime]) The end time for the query as a datetime object.
        :param params: (Optional[dict]) Additional parameters to be sent in the query.
        :returns: (dict) A dictionary of the query results, which includes the series of matched metrics.
        :raises:
            (PrometheusApiClientException) Raises an exception with details of the response, in case of a non 200 HTTP status code.
        """
        params = params or {}

        # The data to be sent with the POST request
        data = {
            'match[]': match,
        }

        # Include start and end time in the data if provided
        if start_time:
            data['start'] = round(start_time.timestamp())
        if end_time:
            data['end'] = round(end_time.timestamp())

        response = self._send_series(data=data, params=params)
        if response.status_code == 200:
            return response.json()["data"]
        else:
            raise PrometheusApiClientException(
                f"Failed to retrieve `series` data from Prometheus. "
                f"Response status: {response.status_code!r}. "
                f"Response content: {response.content!r}.  "
            )

