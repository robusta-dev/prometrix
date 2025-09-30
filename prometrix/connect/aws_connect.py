import os
from datetime import datetime
from typing import Any, Dict, Optional
import logging

import requests
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from prometheus_api_client import PrometheusApiClientException
from botocore.exceptions import BotoCoreError, ClientError

from prometrix.connect.custom_connect import CustomPrometheusConnect

SA_TOKEN_PATH = os.environ.get("SA_TOKEN_PATH", "/var/run/secrets/eks.amazonaws.com/serviceaccount/token")
AWS_ASSUME_ROLE = os.environ.get("AWS_ASSUME_ROLE")

class AWSPrometheusConnect(CustomPrometheusConnect):
    def __init__(
        self,
        access_key: Optional[str],
        secret_key: Optional[str],
        region: str,
        service_name: str,
        token: Optional[str] = None,
        assume_role_arn: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.region = region
        self.service_name = service_name

        if access_key and secret_key:
            # Backwards compatibility: use static keys
            self._credentials = Credentials(access_key, secret_key, token)
            self._has_static_keys = True
            self._session = None
        else:
            # IRSA
            session = boto3.Session()
            creds = session.get_credentials()
            if not creds:
                raise RuntimeError("No AWS credentials found (neither static keys nor IRSA)")
            self._credentials = creds
            self._has_static_keys = False
            self._session = session

        role_to_assume = assume_role_arn or AWS_ASSUME_ROLE
        self._role_to_assume = role_to_assume
        if role_to_assume:
            self._assume_role(role_to_assume)

    def _assume_role(self, role_arn: str) -> None:
        try:
            frozen = self._credentials.get_frozen_credentials()
            sts = boto3.client(
                "sts",
                region_name=self.region,
                aws_access_key_id=frozen.access_key,
                aws_secret_access_key=frozen.secret_key,
                aws_session_token=frozen.token,
            )
            resp = sts.assume_role(RoleArn=role_arn, RoleSessionName="amp-auto")
            credentials = resp.get("Credentials")
            if not credentials:
                logging.error("Invalid assume role response %s", resp)
                return
            required = ["AccessKeyId", "SecretAccessKey", "SessionToken"]
            missing = [f for f in required if not credentials.get(f)]
            if missing:
                logging.error("Missing required credential fields: {missing}. Raw response: {resp}")
                raise Exception(f"Failed to assume role: missing fields {missing}")

            self._credentials = Credentials(
                credentials["AccessKeyId"],credentials["SecretAccessKey"], credentials["SessionToken"]
            )
        except (ClientError, BotoCoreError, Exception) as e:
            raise Exception(f"Failed to assume role {role_arn}: {str(e)}")

    def _build_auth(self) -> SigV4Auth:
        """Builds fresh SigV4 auth with current credentials (handles rotation)."""
        frozen = self._credentials.get_frozen_credentials()
        return SigV4Auth(frozen, self.service_name, self.region)

    def signed_request(
        self, method, url, data=None, params=None, verify=False, headers=None
    ):
        request = AWSRequest(method=method, url=url, data=data, params=params, headers=headers)
        auth = self._build_auth()
        auth.add_auth(request)
        return requests.request(
            method=method,
            url=url,
            headers=dict(request.headers),
            verify=verify,
            data=data,
            params=params,
        )

    def _refresh_credentials(self) -> None:
        """
            Boto should automatically refresh expired credentials but when assuming role it cant be done automatically
        """
        try:
            if not self._has_static_keys and self._session is not None:
                # this is also needed for assume role if base credentials fails
                refreshed = self._session.get_credentials()
                if refreshed:
                    self._credentials = refreshed
        except Exception:
            logging.exception("Failed to refresh session credentials")
        if self._role_to_assume:
            try:
                self._assume_role(self._role_to_assume)
            except Exception:
                logging.exception("Failed to refresh assume role")

    def _request_with_refresh(self, *, method, url, data=None, params=None, headers=None, verify=False):
        resp = self.signed_request(
            method=method,
            url=url,
            data=data,
            params=params,
            verify=verify,
            headers=headers,
        )
        if resp is not None and resp.status_code in (400, 401, 403):
            self._refresh_credentials()
            resp = self.signed_request(
                method=method,
                url=url,
                data=data,
                params=params,
                verify=verify,
                headers=headers,
            )
        return resp

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
        response = self._request_with_refresh(
            method="POST",
            url="{0}/api/v1/query".format(self.url),
            data={**{"query": query}, **params},
            params={},
            verify=self.ssl_verification,
            headers=self.headers,
        )
        return response

    def safe_custom_query_range(
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
        response = self._request_with_refresh(
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
        return self.get_label_values(label_name="__name__", params=params)

    def _send_series(self, data: dict, params: dict) -> requests.Response:
        return self.signed_request(
            method="POST",
            url=f"{self.url}/api/v1/series",
            data=data,
            headers=self.headers,
            params=params,
            verify=self.ssl_verification,
        )

    def get_current_metric_value(self, *args, **kwargs):
        raise NotImplementedError

    def get_metric_range_data(self, *args, **kwargs):
        raise NotImplementedError

    def get_metric_aggregation(self, *args, **kwargs):
        raise NotImplementedError
