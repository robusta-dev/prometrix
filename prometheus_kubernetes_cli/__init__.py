from prometheus_kubernetes_cli.models import (
    AzurePrometheusConfig,
    CoralogixPrometheusConfig,
    PrometheusConfig,
    AWSPrometheusConfig,
    VictoriaMetricsPrometheusConfig,
    PrometheusQueryResult
)
from prometheus_kubernetes_cli.utils import get_custom_prometheus_connect
from prometheus_kubernetes_cli.auth import PrometheusAuthorization
from prometheus_kubernetes_cli.custom_connect import CustomPrometheusConnect, AWSPrometheusConnect
from prometheus_kubernetes_cli.exceptions import MetricsNotFound,PrometheusNotFound,VictoriaMetricsNotFound, ThanosMetricsNotFound,PrometheusFlagsConnectionError