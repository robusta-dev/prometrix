from enum import Enum
import os
from typing import Dict, List, Optional

try:
    # Works if Pydantic v2 is installed
    from pydantic.v1 import BaseModel, SecretStr
except ImportError:
    # Fallback if running under Pydantic v1
    from pydantic import BaseModel, SecretStr


class PrometheusApis(Enum):
    QUERY = 0
    QUERY_RANGE = 1
    LABELS = 2
    FLAGS = 3
    VM_FLAGS = 4


class PrometheusConfig(BaseModel):
    url: str
    disable_ssl: bool = False
    headers: Dict[str, str] = {}
    prometheus_auth: Optional[SecretStr] = None
    prometheus_url_query_string: Optional[str] = None
    additional_labels: Optional[Dict[str, str]] = None
    supported_apis: List[PrometheusApis] = [
        PrometheusApis.QUERY,
        PrometheusApis.QUERY_RANGE,
        PrometheusApis.LABELS,
        PrometheusApis.FLAGS,
    ]
    query_step: str = "5m"
    query_interval: str = "1d"


class AWSPrometheusConfig(PrometheusConfig):
    access_key: Optional[str] = None
    secret_access_key: Optional[str] = None
    token: Optional[str] = None
    service_name: str = "aps"
    aws_region: str
    assume_role_arn: Optional[str] = None
    supported_apis: List[PrometheusApis] = [
        PrometheusApis.QUERY,
        PrometheusApis.QUERY_RANGE,
        PrometheusApis.LABELS,
    ]


class CoralogixPrometheusConfig(PrometheusConfig):
    prometheus_token: str
    supported_apis: List[PrometheusApis] = [
        PrometheusApis.QUERY,
        PrometheusApis.QUERY_RANGE,
        PrometheusApis.LABELS,
    ]


class VictoriaMetricsPrometheusConfig(PrometheusConfig):
    supported_apis: List[PrometheusApis] = [
        PrometheusApis.QUERY,
        PrometheusApis.QUERY_RANGE,
        PrometheusApis.LABELS,
        PrometheusApis.VM_FLAGS,
    ]


# Does not support labels according to the docs, See below for apis
# https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/prometheus-api-promql#supported-apis
class AzurePrometheusConfig(PrometheusConfig):
    azure_resource: str = "https://prometheus.monitor.azure.com"
    azure_metadata_endpoint: str = "http://169.254.169.254/metadata/identity/oauth2/token"
    azure_token_endpoint: str = f"https://login.microsoftonline.com/{os.environ.get('AZURE_TENANT_ID')}/oauth2/token"
    azure_use_managed_id: Optional[bool] = False
    azure_use_workload_id: Optional[bool] = False
    azure_client_id: Optional[str] = None
    azure_tenant_id: Optional[str] = os.environ.get('AZURE_TENANT_ID', '')
    azure_client_secret: Optional[str] = None
    supported_apis: List[PrometheusApis] = [
        PrometheusApis.QUERY,
        PrometheusApis.QUERY_RANGE,
    ]
