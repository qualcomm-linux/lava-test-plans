from lava_test_plans.__main__ import main

import os
import shlex
import sys

import pytest
from ruamel.yaml import YAML

device = "dragonboard-845c"
testplan = "meta-qcom/nodistro/boot"
project_device_path = "lava_test_plans/projects/meta-qcom/devices"
project_variables = "projects/meta-qcom/variables.yaml"


def render_queue_timeout(tmp_path, *overwrite_variables):
    """Render one meta-qcom job and return its queue timeout."""
    overwrite = ""
    if overwrite_variables:
        overwrite = "--overwrite-variables " + " ".join(overwrite_variables)
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --variables "{project_variables}" '
        f'--testplan-device-path "{project_device_path}" '
        f'--device-type "{device}" --test-plan "{testplan}" '
        f'--dry-run-path "{tmp_path}" {overwrite}'
    )
    assert main() == 0
    job = os.path.join(tmp_path, device, "boot.yaml")
    with open(job) as job_file:
        return YAML(typ="safe").load(job_file)["timeouts"].get("queue")


@pytest.mark.parametrize(
    "variables,queue",
    [
        ((), None),
        (("LAVA_QUEUE_TIMEOUT=2",), {"hours": 2}),
        (("LAVA_QUEUE_TIMEOUT_MINUTES=45",), {"minutes": 45}),
        (
            ("LAVA_QUEUE_TIMEOUT=2", "LAVA_QUEUE_TIMEOUT_MINUTES=45"),
            {"minutes": 45},
        ),
    ],
    ids=["unset", "hours", "minutes", "minutes-wins"],
)
def test_queue_timeout(tmp_path, variables, queue):
    assert render_queue_timeout(tmp_path, *variables) == queue
