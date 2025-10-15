from lava_test_plans.__main__ import main

from unittest import TestCase
import sys
import glob
import os
import pytest
import shlex

test_lava_validity = (
    "" if os.getenv("SKIP_TEST_LAVA_VALIDITY") else "--test-lava-validity"
)

# all Linux tests all devices
devices = [os.path.basename(d) for d in glob.glob("lava_test_plans/devices/*")]
testcases = [
    os.path.basename(d)
    for d in glob.glob("lava_test_plans/testcases/[!android-]*.yaml")
]
variable_input_file = "variables.ini"
tests = []
for device in devices:
    if device == "variables":
        continue
    for testcase in testcases:
        tests.append((variable_input_file, device, testcase))


@pytest.mark.parametrize("param", tests)
def test_call_lava_test_plan_testcases(param):
    variable_input_file, device, testcase = param
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --variables "{variable_input_file}" --device-type "{device}" --test-case "{testcase}"'
    )
    assert main() == 0


# lt-qcom tests
lt_qcom_project_device_path = "lava_test_plans/projects/lt-qcom/devices"
lt_qcom_devices = [
    os.path.basename(d) for d in glob.glob("lava_test_plans/projects/lt-qcom/devices/*")
]
assert len(lt_qcom_devices) > 0
lt_qcom_testplans = ["lt-qcom/kernel"]
assert len(lt_qcom_testplans) > 0
lt_qcom_variable_input_file = "projects/lt-qcom/variables.yaml"
tests = []
for device in lt_qcom_devices:
    for testplan in lt_qcom_testplans:
        tests.append(
            (lt_qcom_variable_input_file, device, testplan, lt_qcom_project_device_path)
        )


@pytest.mark.parametrize("param", tests)
def test_call_lava_test_plan_testplans_project_lt_qcom(param):
    variable_input_file, device, testplan, project_device_path = param
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --variables "{variable_input_file}" --testplan-device-path "{project_device_path}" --device-type "{device}" --test-plan "{testplan}" {test_lava_validity}'
    )
    assert main() == 0
