import json
import shlex
import sys

from ruamel.yaml import YAML

from lava_test_plans.__main__ import main


def test_param_with_quotes(tmp_path):
    # The params are quoted with tojson: a double quote, a single quote or a
    # backslash in a value must not break the job.
    password = "p\"w'&x\\"
    extra = tmp_path / "wifi.yaml"
    extra.write_text(json.dumps({"WIFI_SSID_PASSWORD": password}))
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --dry-run-path "{tmp_path}" '
        f'--variables variables.ini "{extra}" '
        "--device-type qcs6490-rb3gen2 --test-case connectivity-wifi.yaml"
    )
    assert main() == 0
    job = YAML(typ="safe").load(
        open(tmp_path / "qcs6490-rb3gen2" / "connectivity-wifi.yaml")
    )
    params = [
        d["params"]
        for a in job["actions"]
        for d in a.get("test", {}).get("definitions", [])
        if "params" in d
    ]
    assert any(p.get("PASSWORD") == password for p in params), params
