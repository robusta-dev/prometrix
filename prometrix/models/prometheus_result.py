import json
from typing import Dict, List, Optional

PrometheusMetric = Dict[str, str]


class PrometheusScalarValue:
    def __init__(self, raw_scalar_list: List):
        """
        Initialize a Prometheus scalar value.
        The scalar is expected to be a list where the first element is a timestamp and the second is the value.
        """
        if len(raw_scalar_list) != 2:
            raise ValueError(f"Invalid prometheus scalar value {raw_scalar_list}")
        self.timestamp = float(raw_scalar_list[0])
        self.value = str(raw_scalar_list[1])

    def to_dict(self):
        """ Convert scalar value to a dictionary for JSON """
        return {
            "timestamp": self.timestamp,
            "value": self.value
        }

class PrometheusSeries:
    def __init__(self, metric: Dict[str, str], values: List):
        """
        Initialize a Prometheus series object.
        :param metric: Dictionary of metric labels.
        :param values: List of [timestamp, value] pairs.
        """
        self.metric = metric
        self.timestamps = [float(value[0]) for value in values]
        self.values = [str(value[1]) for value in values]

    def to_dict(self):
        """ Convert series object to a dictionary for JSON """
        return {
            "metric": self.metric,
            "timestamps": self.timestamps,
            "values": self.values
        }

class PrometheusQueryResult:
    def __init__(self, data: Dict):
        result = data.get("result", None)
        result_type = data.get("resultType", None)

        if not result_type:
            raise ValueError("resultType missing")
        if result is None:
            raise ValueError("result object missing")

        self.result_type = result_type
        self.vector_result = None
        self.series_list_result = None
        self.scalar_result = None
        self.string_result = None

        if result_type == "string" or result_type == "error":
            self.string_result = str(result)
        elif result_type == "scalar" and isinstance(result, list):
            self.scalar_result = PrometheusScalarValue(result).to_dict()
        elif result_type == "vector" and isinstance(result, list):
            self.vector_result = self._format_vector(result)
        elif result_type == "matrix" and isinstance(result, list):
            self.series_list_result = self._format_series(result)
        else:
            raise ValueError("result or returnType is invalid")

    def _format_vector(self, vector: List):
        """ Convert vector result into a list of dictionaries for JSON """
        return [
            {
                "metric": vector_item["metric"],
                "value": PrometheusScalarValue(vector_item["value"]).to_dict()
            }
            for vector_item in vector
        ]

    def _format_series(self, series: List):
        """ Convert matrix (series) result into a list of PrometheusSeries dictionaries for JSON """
        return [
            PrometheusSeries(series_item["metric"], series_item["values"]).to_dict()
            for series_item in series
        ]

    def to_json(self):
        """ Return the result as a JSON-compatible dictionary """
        return json.dumps({
            "result_type": self.result_type,
            "vector_result": self.vector_result,
            "series_list_result": self.series_list_result,
            "scalar_result": self.scalar_result,
            "string_result": self.string_result
        }, indent=4)