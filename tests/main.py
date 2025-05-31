import os.path
import sys
from datetime import datetime, timedelta
from typing import Dict

import yaml
from prometheus_api_client import PrometheusApiClientException
from pydantic import ValidationError
from pytimeparse.timeparse import timeparse

from prometrix import (AWSPrometheusConfig, AzurePrometheusConfig,
                       CoralogixPrometheusConfig, CustomPrometheusConnect,
                       PrometheusApis, PrometheusConfig, PrometheusNotFound,
                       PrometheusQueryResult, get_custom_prometheus_connect)


def generate_prometheus_config(
    config_type: str, params: Dict[str, str]
) -> PrometheusConfig:
    if config_type == "AWSPrometheusConfig":
        return AWSPrometheusConfig(**params)
    if config_type == "CoralogixPrometheusConfig":
        return CoralogixPrometheusConfig(**params)
    if config_type == "AzurePrometheusConfig":
        return AzurePrometheusConfig(**params)
    return PrometheusConfig(**params)


def test_label(prom: CustomPrometheusConnect) -> bool:
    if PrometheusApis.LABELS in prom.config.supported_apis:
        return len(prom.get_label_values("pod")) > 0
    try:
        prom.get_label_values("pod")
        return False
    except PrometheusApiClientException:
        return True


def check_result_not_empty(result: PrometheusQueryResult) -> bool:
    if result.result_type != "matrix":
        print(
            f"Prometheus tests for results of type {result.result_type} not supported yet"
        )
        return False
    for series in result.series_list_result:
        if len(series["values"]) > 1 and len(series["timestamps"]) > 1:
            return True
    return False


def run_test(test_type: str, config: PrometheusConfig) -> bool:
    try:
        prom_cli = get_custom_prometheus_connect(config)
        prom_cli.check_prometheus_connection()
        if not test_label(prom_cli):
            print(f"Test {test_type} failed, error with label api")
            return False
        result = prom_cli.safe_custom_query_range(
            query="container_memory_working_set_bytes",
            start_time=datetime.now() - timedelta(seconds=timeparse(config.query_interval)),
            end_time=datetime.now(),
            step=config.query_step,
        )
        formatted_result = PrometheusQueryResult(data=result)
        if not check_result_not_empty(formatted_result):
            print(f"Test {test_type} failed, empty or invalid results")
            return False
        print(f"Test {test_type} passed")
        return True
    except PrometheusNotFound:
        print(f"Test {test_type} failed, could not connect to prometheus")
        return False
    except ValidationError:
        print(f"Test {test_type} failed, results of wrong format")
        return False


def main(config_file="config.yaml"):
    print(f"Using config file {config_file}")
    if not os.path.isfile(config_file):
        print(
            "To run tests you must create a test config file.\n See 'test_config_example.yaml' for "
            "the format and examples"
        )
        return
    with open(config_file, "r") as tests_yaml_file:
        yaml_obj = yaml.safe_load(
            tests_yaml_file
        )  # yaml_object will be a list or a dict

    overall_test_result = True

    for test_config in yaml_obj["testConfig"]:
        config_type = test_config["type"]
        config_params = test_config["params"]
        config = generate_prometheus_config(config_type, config_params)
        result = run_test(config_type, config)
        overall_test_result = overall_test_result and result

    sys.exit(0 if overall_test_result else 1)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        main(config_file=sys.argv[1])
    else:
        main()
