from datetime import datetime
from typing import Any, Dict, Optional, List

import requests
from botocore.auth import S3SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from prometheus_api_client import PrometheusApiClientException

from prometrix.connect.custom_connect import CustomPrometheusConnect


class AWSPrometheusConnect(CustomPrometheusConnect):
    def __init__(
        self, access_key: str, secret_key: str, region: str, service_name: str, **kwargs
    ):
        super().__init__(**kwargs)
        self._credentials = Credentials(access_key, secret_key)
        self._sigv4auth = S3SigV4Auth(self._credentials, service_name, region)

    def signed_request(
        self, method, url, data=None, params=None, verify=False, headers=None
    ):
        request = AWSRequest(
            method=method, url=url, data=data, params=params, headers=headers
        )
        self._sigv4auth.add_auth(request)
        return requests.request(
            method=method,
            url=url,
            headers=dict(request.headers),
            verify=verify,
            data=data,
        )

    def _custom_query(self, query: str, params: dict = None):
        """
        Send a custom query to a Prometheus Host.

        This method takes as input a string which will be sent as a query to
        the specified Prometheus Host. This query is a PromQL query.

        :param query: (str) This is a PromQL query, a few examples can be found
            at https://prometheus.io/docs/prometheus/latest/querying/examples/
        :param params: (dict) Optional dictionary containing GET parameters to be
            sent along with the API request, such as "time"
        :returns: (list) A list of metric data received in response of the query sent
        :raises:
            (RequestException) Raises an exception in case of a connection error
            (PrometheusApiClientException) Raises in case of non 200 response status code
        """
        params = params or {}
        data = None
        query = str(query)
        # using the query API to get raw data
        response = self.signed_request(
            method="POST",
            url="{0}/api/v1/query".format(self.url),
            data={**{"query": query}, **params},
            params={},
            verify=self.ssl_verification,
            headers=self.headers,
        )
        return response

    def custom_query_range(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        step: str,
        params: Optional[Dict[str, Any]] = None,
    ):
        """
        Send a query_range to a Prometheus Host.
        This method takes as input a string which will be sent as a query to
        the specified Prometheus Host. This query is a PromQL query.
        :param query: (str) This is a PromQL query, a few examples can be found
            at https://prometheus.io/docs/prometheus/latest/querying/examples/
        :param start_time: (datetime) A datetime object that specifies the query range start time.
        :param end_time: (datetime) A datetime object that specifies the query range end time.
        :param step: (str) Query resolution step width in duration format or float number of seconds - i.e 100s, 3d, 2w, 170.3
        :param params: (dict) Optional dictionary containing GET parameters to be
            sent along with the API request, such as "timeout"
        :returns: (dict) A dict of metric data received in response of the query sent
        :raises:
            (RequestException) Raises an exception in case of a connection error
            (PrometheusApiClientException) Raises in case of non 200 response status code
        """
        start = round(start_time.timestamp())
        end = round(end_time.timestamp())
        params = params or {}

        query = str(query)
        response = self.signed_request(
            method="POST",
            url="{0}/api/v1/query_range".format(self.url),
            data={
                **{"query": query, "start": start, "end": end, "step": step},
                **params,
            },
            params={},
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

    def get_label_values(self, label_name: str, params: dict = None):
        params = params or {}
        response = self.signed_request(
            method="GET",
            url="{0}/api/v1/label/{1}/values".format(self.url, label_name),
            verify=self.ssl_verification,
            headers=self.headers,
            params=params,
        )
        if response.status_code == 200:
            return response.json()["data"]
        else:
            raise PrometheusApiClientException(
                "HTTP Status Code {} ({!r})".format(
                    response.status_code, response.content
                )
            )

    def all_metrics(self, params: dict = None):
        """
        Get the list of all the metrics that the prometheus host scrapes.

        :param params: (dict) Optional dictionary containing GET parameters to be
            sent along with the API request, such as "time"
        :returns: (list) A list of names of all the metrics available from the
            specified prometheus host
        :raises:
            (RequestException) Raises an exception in case of a connection error
            (PrometheusApiClientException) Raises in case of non 200 response status code
        """
        self._all_metrics = self.get_label_values(label_name="__name__", params=params)
        return self._all_metrics

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

        response = self.signed_request(
            method="POST",
            url=f"{self.url}/api/v1/series",
            data=data,
            headers=self.headers,
            params=params,
            verify=self.ssl_verification,
        )
        if response.status_code == 200:
            return response.json()["data"]
        else:
            raise PrometheusApiClientException(
                f"Failed to retrieve `series` data from Prometheus. "
                f"Response status: {response.status_code!r}. "
                f"Response content: {response.content!r}.  "
            )

    def get_current_metric_value(self, *args, **kwargs):
        raise NotImplementedError

    def get_metric_range_data(self, *args, **kwargs):
        raise NotImplementedError

    def get_metric_aggregation(self, *args, **kwargs):
        raise NotImplementedError
