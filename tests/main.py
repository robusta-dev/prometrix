import json
from datetime import datetime, timedelta
from typing import Dict
from pydantic import ValidationError
import yaml
import os.path
from prometrix import (AWSPrometheusConfig, AzurePrometheusConfig,
                       CoralogixPrometheusConfig, PrometheusConfig,
                       PrometheusNotFound, PrometheusQueryResult,
                       get_custom_prometheus_connect)


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


def check_result_not_empty(result: PrometheusQueryResult) -> bool:
    if result.result_type != "matrix":
        print(f"Prometheus tests for results of type {result.result_type} not supported yet")
        return False
    for series in result.series_list_result:
        if len(series.values) > 1 and len(series.timestamps) > 1:
            return True
    return False


def run_test(test_type: str, config: PrometheusConfig):
    try:
        prom_cli = get_custom_prometheus_connect(config)
        prom_cli.check_prometheus_connection()
        result = prom_cli.custom_query_range(
            query="container_memory_working_set_bytes",
            start_time=datetime.now() - timedelta(days=1),
            end_time=datetime.now(),
            step="5m",
        )
        formatted_result = PrometheusQueryResult(data=result)
        if not check_result_not_empty(formatted_result):
            print(f"Test {test_type} failed, empty or invalid results")
        print(f"Test {test_type} passed")
    except PrometheusNotFound:
        print(f"Test {test_type} failed, could not connect to prometheus")
    except ValidationError:
        print(f"Test {test_type} failed, results of wrong format")


def main():
    test_config_file_name="config.yaml"
    if not os.path.isfile(test_config_file_name):
        print(f"To run tests you must create a test config file called '{test_config_file_name}'.\n See 'test_config_example.yaml' for the format and examples")
        return

    with open(test_config_file_name, "r") as tests_yaml_file:
        yaml_obj = yaml.safe_load(
            tests_yaml_file
        )  # yaml_object will be a list or a dict
        for test_config in yaml_obj["testConfig"]:
            config_type = test_config["type"]
            config_params = test_config["params"]
            config = generate_prometheus_config(config_type, config_params)
            run_test(config_type, config)


if __name__ == "__main__":
    main()
