from lava_test_plans.__main__ import main
from lava_test_plans.utils import merge_variables

import os
import shlex
import sys

import pytest
from ruamel.yaml import YAML

device = "dragonboard-845c"
testplan = "meta-qcom/nodistro/boot"
project_device_path = "lava_test_plans/projects/meta-qcom/devices"
project_variables = "projects/meta-qcom/variables.yaml"


def render(tmp_path, *variable_files):
    """Render one meta-qcom job and return its metadata."""
    variables = " ".join(f'"{f}"' for f in (project_variables, *variable_files))
    sys.argv = shlex.split(
        f"lava_test_plans --dry-run --variables {variables} "
        f'--testplan-device-path "{project_device_path}" '
        f'--device-type "{device}" --test-plan "{testplan}" '
        f'--dry-run-path "{tmp_path}"'
    )
    assert main() == 0
    job = os.path.join(tmp_path, device, "boot.yaml")
    with open(job) as job_file:
        return YAML(typ="safe").load(job_file)["metadata"]


def test_extra_metadata_from_ini_section(tmp_path):
    metadata = render(tmp_path, "test/variables-extra-metadata.ini")
    assert metadata["kernel-recipe"] == "linux-qcom"
    assert metadata["kernel-commit"] == "8a3c8dae4f"
    # a quoted value keeps its commas instead of being read as a list
    assert metadata["kernel-config"] == "defconfig, distro.config"


def test_extra_metadata_from_yaml_mapping(tmp_path):
    metadata = render(tmp_path, "test/variables-extra-metadata.yaml")
    assert metadata["kernel-release"] == "6.18.0"
    assert metadata["source-sha"] == "1b0e4f9c2d"


def test_extra_metadata_does_not_overwrite_a_named_key(tmp_path):
    metadata = render(tmp_path, "test/variables-extra-metadata.ini")
    # the file sets a key the job already names: the named value is kept and
    # the job still renders, rather than emitting the key twice and failing
    assert metadata["build-url"] == "https://some-url"


def test_extra_metadata_files_are_merged(tmp_path):
    metadata = render(
        tmp_path,
        "test/variables-extra-metadata.ini",
        "test/variables-extra-metadata.yaml",
    )
    assert metadata["kernel-recipe"] == "linux-qcom"
    assert metadata["kernel-release"] == "6.18.0"


def test_named_metadata_keys_are_always_present(tmp_path):
    metadata = render(tmp_path)
    assert metadata["pr-url"] == ""
    assert "kernel-recipe" not in metadata


@pytest.mark.parametrize(
    "value",
    ["yes", "6.18", "0755", "123"],
    ids=["bool-like", "float-like", "octal-like", "int-like"],
)
def test_extra_metadata_values_stay_strings(tmp_path, value):
    variables = tmp_path / "extra.ini"
    variables.write_text(f'[EXTRA_METADATA]\nkernel-release = "{value}"\n')
    metadata = render(tmp_path / "jobs", str(variables))
    assert metadata["kernel-release"] == value


def test_merge_variables_merges_mappings_and_overwrites_values():
    context = {"EXTRA_METADATA": {"a": "1", "b": "2"}, "BUILD_URL": "first"}
    merge_variables(context, {"EXTRA_METADATA": {"b": "3", "c": "4"}})
    merge_variables(context, {"BUILD_URL": "second"})
    assert context["EXTRA_METADATA"] == {"a": "1", "b": "3", "c": "4"}
    assert context["BUILD_URL"] == "second"
