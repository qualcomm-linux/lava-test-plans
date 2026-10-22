import shlex
import sys

from ruamel.yaml import YAML

from lava_test_plans.__main__ import main


def render(tmp_path, extra=""):
    variables = tmp_path / "overlays.yaml"
    variables.write_text(extra or "{}\n")
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --dry-run-path "{tmp_path}" '
        '--variables "projects/meta-qcom-arduino/variables.yaml" '
        f'"{variables}" '
        '--testplan-device-path "lava_test_plans/projects/meta-qcom-arduino/devices" '
        "--device-type ventuno-q --test-case boot.yaml"
    )
    assert main() == 0
    job = YAML(typ="safe").load(open(tmp_path / "ventuno-q" / "boot.yaml"))
    return job["actions"][0]["deploy"]["qcomflash"]


def test_without_overlays(tmp_path):
    qcomflash = render(tmp_path)
    assert qcomflash["apply-overlay"] is True
    assert "overlays" not in qcomflash and "format" not in qcomflash


def test_with_overlays(tmp_path):
    qcomflash = render(
        tmp_path,
        '"qdl_overlays": {"sdk": {"url": "https://example.invalid/sdk.zip",'
        ' "format": "file", "path": "/sdk/sdk.zip"}}\n',
    )
    assert "apply-overlay" not in qcomflash
    assert qcomflash["format"] == "ext4"
    assert qcomflash["overlays"] == {
        "lava": True,
        "sdk": {
            "url": "https://example.invalid/sdk.zip",
            "format": "file",
            "path": "/sdk/sdk.zip",
        },
    }
