import glob
import os
import shlex
import sys

import pytest
from ruamel.yaml import YAML

from lava_test_plans.__main__ import main
from test.validity_helpers import (
    test_lava_validity,
    test_lava_validity_container,
)

PROJECT = "lava_test_plans/projects/open-boot-stack"
DEVICE_PATH = PROJECT + "/devices"
VARIABLES = "projects/open-boot-stack/variables.yaml"
DEVICES = sorted(os.path.basename(d) for d in glob.glob(DEVICE_PATH + "/*"))
TESTPLANS = [
    "open-boot-stack/full",
    "open-boot-stack/maxcpus",
    "open-boot-stack/memtest",
    "open-boot-stack/negative",
]


def render(device, args, out):
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --dry-run-path "{out}" '
        f'--variables "{VARIABLES}" "projects/open-boot-stack/boards/{device}.yaml" '
        f'--testplan-device-path "{DEVICE_PATH}" --device-type "{device}" {args}'
    )
    return main()


def load(path):
    return YAML(typ="safe").load(open(path))


def definitions(job):
    return [
        d["name"]
        for action in job["actions"]
        for d in action.get("test", {}).get("definitions", [])
    ]


def test_every_device_has_board_facts():
    assert DEVICES
    for device in DEVICES:
        assert os.path.exists(f"{PROJECT}/boards/{device}.yaml"), device


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("testplan", TESTPLANS)
def test_open_boot_stack_testplans(device, testplan, tmp_path):
    args = (
        f'--test-plan "{testplan}" {test_lava_validity} {test_lava_validity_container}'
    )
    assert render(device, args, tmp_path) == 0


def test_full_job(tmp_path):
    assert render("ventuno-q", "--test-case open-boot-stack.yaml", tmp_path) == 0
    job = load(tmp_path / "ventuno-q" / "open-boot-stack.yaml")
    names = definitions(job)
    assert names[:2] == ["boot-fingerprint", "boot-handoff"]
    assert names[-3:] == [
        "boot-fingerprint-after-reboot",
        "boot-handoff-after-reboot",
        "kernel-health-after-reboot",
    ]
    assert len(names) == len(set(names))
    monitors = [
        m for a in job["actions"] for m in a.get("test", {}).get("monitors", [])
    ]
    assert [m["name"] for m in monitors] == [
        "firmware-fingerprint-cold",
        "firmware-fingerprint-warm",
    ]
    assert monitors[0]["expected"] == ["bl2", "bl31", "op_tee_version", "u_boot"]
    assert monitors[0]["fixupdict"] == {"OBSFP-000000-000000": "pass"}


def test_excluded_and_absent_tests(tmp_path):
    # rb3gen2 excludes alsa-dsp-restart in its device file; qcs615-ride has
    # no video facts and excludes video-codec.
    assert render("rb3gen2", "--test-case open-boot-stack.yaml", tmp_path) == 0
    assert "alsa-dsp-restart" not in definitions(
        load(tmp_path / "rb3gen2" / "open-boot-stack.yaml")
    )
    assert render("qcs615-ride", "--test-case open-boot-stack.yaml", tmp_path) == 0
    names = definitions(load(tmp_path / "qcs615-ride" / "open-boot-stack.yaml"))
    assert "video-codec" not in names and "fastrpc" not in names


def test_stage_fingerprints(tmp_path):
    vars_file = tmp_path / "build.yaml"
    vars_file.write_text(
        '"FIRMWARE_FINGERPRINT": "FW-1"\n'
        '"STAGE_FINGERPRINTS": {"OP-TEE version": "TEE-2", "U-Boot": "UB-3"}\n'
    )
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --dry-run-path "{tmp_path}" '
        f'--variables "{VARIABLES}" "projects/open-boot-stack/boards/ventuno-q.yaml" "{vars_file}" '
        f'--testplan-device-path "{DEVICE_PATH}" --device-type ventuno-q --test-case open-boot-stack.yaml'
    )
    assert main() == 0
    job = load(tmp_path / "ventuno-q" / "open-boot-stack.yaml")
    monitor = job["actions"][3]["test"]["monitors"][0]
    assert "OP-TEE version(?=[^\\r\\n]*?TEE-2)" in monitor["pattern"]
    assert "U-Boot(?=[^\\r\\n]*?UB-3)" in monitor["pattern"]
    assert "BL31(?=[^\\r\\n]*?FW-1)" in monitor["pattern"]
    assert sorted(monitor["fixupdict"]) == ["FW-1", "TEE-2", "UB-3"]
    fingerprint = job["actions"][5]["test"]["definitions"][0]
    # The SMBIOS BIOS version is U-Boot's.
    assert fingerprint["params"]["FIRMWARE_FINGERPRINT"] == "UB-3"


def test_qairt_overlay_only_with_qnn(tmp_path):
    # The QAIRT zip is downloaded as a file overlay only for boards with a
    # QNN entry; the others keep the plain LAVA overlay.
    for device, qnn in (("ventuno-q", True), ("uno-q", False)):
        assert render(device, "--test-case open-boot-stack.yaml", tmp_path) == 0
        job = load(tmp_path / device / "open-boot-stack.yaml")
        qcomflash = job["actions"][0]["deploy"]["qcomflash"]
        inference = [
            d
            for a in job["actions"]
            for d in a.get("test", {}).get("definitions", [])
            if d["name"] == "inference"
        ][0]
        if qnn:
            assert qcomflash["format"] == "ext4"
            assert qcomflash["overlays"]["lava"] is True
            assert qcomflash["overlays"]["qairt"]["format"] == "file"
            assert (
                inference["params"]["QAIRT_ZIP"]
                == "/lava-ovl" + qcomflash["overlays"]["qairt"]["path"]
            )
        else:
            assert qcomflash["apply-overlay"] is True
            assert "overlays" not in qcomflash
            assert inference["params"]["QAIRT_ZIP"] == ""


def test_inference_negative(tmp_path):
    names = {}
    for device in ("ventuno-q", "uno-q"):
        assert (
            render(
                device, "--test-case open-boot-stack-inference-negative.yaml", tmp_path
            )
            == 0
        )
        job = load(tmp_path / device / "open-boot-stack-inference-negative.yaml")
        names[device] = definitions(job)
    assert names["ventuno-q"] == [
        "boot-fingerprint",
        "inference-htp-down",
        "inference-gpu-down",
        "inference-wrong-class",
    ]
    # No NSP on the UNO Q: no htp-down control.
    assert names["uno-q"] == [
        "boot-fingerprint",
        "inference-gpu-down",
        "inference-wrong-class",
    ]


def test_remoteproc_restart_runs_remoteproc_smoke(tmp_path):
    # remoteproc-smoke restarts the remoteprocs when ITERATIONS is above 0.
    assert render("rb3gen2", '--test-case "open-boot-stack.yaml"', tmp_path) == 0
    job = load(tmp_path / "rb3gen2" / "open-boot-stack.yaml")
    (restart,) = [
        d
        for a in job["actions"]
        for d in a.get("test", {}).get("definitions", [])
        if d["name"] == "remoteproc-restart"
    ]
    assert restart["path"].endswith("remoteproc-smoke/remoteproc-smoke.yaml")
    assert restart["params"]["ITERATIONS"] == "3"
