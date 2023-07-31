import json
from typing import Dict

import yaml

from prometrix import (AWSPrometheusConfig, CoralogixPrometheusConfig,
                       PrometheusConfig, PrometheusNotFound, AzurePrometheusConfig,
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


def run_test(test_type: str, config: PrometheusConfig):
    try:
        prom_cli = get_custom_prometheus_connect(config)
        prom_cli.check_prometheus_connection()
        print(f"Test {test_type} passed")
    except PrometheusNotFound:
        print(f"Test {test_type} failed")


def main():
    with open("config.yaml", "r") as tests_yaml_file:
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
