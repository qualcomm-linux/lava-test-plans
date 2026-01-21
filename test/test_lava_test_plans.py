from lava_test_plans.__main__ import main

from unittest import TestCase
from unittest.mock import patch, MagicMock
import sys
import glob
import os
import pytest
import shlex
import tempfile

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


# meta-qcom tests
meta_qcom_project_device_path = "lava_test_plans/projects/meta-qcom/devices"
meta_qcom_devices = [
    os.path.basename(d)
    for d in glob.glob("lava_test_plans/projects/meta-qcom/devices/*")
]
assert len(meta_qcom_devices) > 0
meta_qcom_testplans = [
    "meta-qcom/poky-altcfg/boot",
    "meta-qcom/qcom-distro/boot",
    "meta-qcom/qcom-distro/pre-merge",
]
assert len(meta_qcom_testplans) > 0
meta_qcom_variable_input_file = "projects/meta-qcom/variables.yaml"
tests = []
for device in meta_qcom_devices:
    for testplan in meta_qcom_testplans:
        tests.append(
            (
                meta_qcom_variable_input_file,
                device,
                testplan,
                meta_qcom_project_device_path,
            )
        )


@pytest.mark.parametrize("param", tests)
def test_call_lava_test_plan_testplans_project_meta_qcom(param):
    variable_input_file, device, testplan, project_device_path = param
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --variables "{variable_input_file}" --testplan-device-path "{project_device_path}" --device-type "{device}" --test-plan "{testplan}" {test_lava_validity}'
    )
    assert main() == 0


# qcom-deb-images tests
qcom_deb_images_project_device_path = "lava_test_plans/projects/qcom-deb-images/devices"
qcom_deb_images_devices = [
    os.path.basename(d)
    for d in glob.glob("lava_test_plans/projects/qcom-deb-images/devices/*")
]
assert len(qcom_deb_images_devices) > 0
qcom_deb_images_testplans = ["qcom-deb-images"]
assert len(qcom_deb_images_testplans) > 0
qcom_deb_images_variable_input_file = "projects/qcom-deb-images/variables.yaml"
tests = []
for device in qcom_deb_images_devices:
    for testplan in qcom_deb_images_testplans:
        tests.append(
            (
                qcom_deb_images_variable_input_file,
                device,
                testplan,
                qcom_deb_images_project_device_path,
            )
        )


@pytest.mark.parametrize("param", tests)
def test_call_lava_test_plan_testplans_project_qcom_deb_images(param):
    variable_input_file, device, testplan, project_device_path = param
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --variables "{variable_input_file}" --testplan-device-path "{project_device_path}" --device-type "{device}" --test-plan "{testplan}" {test_lava_validity}'
    )
    assert main() == 0
