import shlex
import subprocess
import sys
from unittest.mock import patch

from ruamel.yaml import YAML

from lava_test_plans.__main__ import main

PROJECT = "projects/meta-qcom-arduino"


def render(tmp_path, mode=None, extra_variables=""):
    variables = f"{PROJECT}/variables.yaml"
    if mode is not None or extra_variables:
        extra = tmp_path / "extra.yaml"
        extra.write_text(
            (f"SUSPEND_MODE: {mode}\n" if mode is not None else "") + extra_variables
        )
        variables += f" {extra}"
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --dry-run-path "{tmp_path}" '
        f"--variables {variables} "
        f'--testplan-device-path "lava_test_plans/{PROJECT}/devices" '
        f'--device-type ventuno-q --test-plan "meta-qcom-arduino/qcom-distro/suspend"'
    )
    assert main() == 0
    path = tmp_path / "ventuno-q" / "suspend-resume.yaml"
    return YAML(typ="safe").load(open(path))


def steps(job):
    out = []
    for action in job["actions"]:
        if "command" in action:
            out.append(action["command"]["name"])
        for d in action.get("test", {}).get("definitions", []):
            out.append(d["name"])
        for i in action.get("test", {}).get("interactive", []):
            out.append(i["name"])
    return out


def suspend_commands(job):
    return [
        s["command"]
        for action in job["actions"]
        for i in action.get("test", {}).get("interactive", [])
        for s in i["script"]
        if s["name"].endswith("-entry")
    ]


def definitions(job):
    return [
        d
        for action in job["actions"]
        for d in action.get("test", {}).get("definitions", [])
    ]


def test_default_mode(tmp_path):
    # One cycle per job, with time for the board to suspend before the
    # wake and to resume after it.
    job = render(tmp_path)
    assert steps(job) == [
        "pre-suspend-check-default",
        "suspend-default",
        "wait_resume",
        "wake_up",
        "wait_resume",
        "resume-default",
        "shell-default",
        "resume-check-default",
    ]
    (command,) = suspend_commands(job)
    assert "mem_sleep" not in command
    assert "echo mem > /sys/power/state" in command


def test_one_cycle_in_the_mode(tmp_path):
    job = render(tmp_path, "deep")
    (command,) = suspend_commands(job)
    assert "echo deep > /sys/power/mem_sleep" in command
    assert [d["name"] for d in definitions(job)] == [
        "pre-suspend-check-deep",
        "resume-check-deep",
    ]


@patch("lava_test_plans.__main__.resolve_git_revision", return_value=None)
def test_testkit_definitions(_resolve, tmp_path):
    # The checks come from the project's qcom-linux-testkit, told the mode.
    job = render(tmp_path, "s2idle", "TEST_DEFINITIONS_REVISION: suspend\n")
    testkit = "https://github.com/qualcomm-linux/qcom-linux-testkit/"
    suite = "Runner/suites/Kernel/Baseport"
    assert definitions(job) == [
        {
            "from": "git",
            "name": "pre-suspend-check-s2idle",
            "path": f"{suite}/Pre_Suspend_Check/Pre_Suspend_Check.yaml",
            "repository": testkit,
            "revision": "suspend",
            "parameters": {"SUSPEND_MODE": "s2idle"},
            "expected": ["Pre_Suspend_Check_s2idle"],
        },
        {
            "from": "git",
            "name": "resume-check-s2idle",
            "path": f"{suite}/Resume_Check/Resume_Check.yaml",
            "repository": testkit,
            "revision": "suspend",
            "parameters": {"SUSPEND_MODE": "s2idle"},
            "expected": ["Resume_Check_s2idle"],
        },
    ]


@patch("lava_test_plans.__main__.resolve_git_revision", return_value="0123abc")
def test_testkit_archive(_resolve, tmp_path):
    # With the revision resolved, the definitions share the archive the
    # other test cases fetch.
    job = render(tmp_path)
    archive = (
        "https://github.com/qualcomm-linux/qcom-linux-testkit/archive/0123abc.tar.gz"
    )
    for d in definitions(job):
        assert d["from"] == "url"
        assert d["repository"] == archive
        assert d["strip-components"] == 1


def test_prompts(tmp_path):
    # The console echoes the command, so the markers must not match their
    # own echo; the last step hands the test shell the image's prompt.
    job = render(tmp_path)
    prompts = [
        p
        for action in job["actions"]
        for i in action.get("test", {}).get("interactive", [])
        for p in i["prompts"]
    ]
    assert prompts == [
        "PM: suspend entry",
        "lava-resumed-3",
        "root@ventuno-q",
        "root@(.*):[/~]#",
    ]
    (command,) = suspend_commands(job)
    for marker in (
        "PM: suspend entry",
        "lava-resumed-3",
        "lava-suspend-failed-3",
        "lava-suspend-unsupported-3",
    ):
        assert marker not in command


def test_failed_suspend_stops_the_job(tmp_path):
    # A mode the kernel does not offer stops the entry step; a write that
    # fails, before the suspend entry or after it (a device fails to
    # suspend), stops whichever step is waiting.
    job = render(tmp_path, "s2idle")
    scripts = [
        s
        for action in job["actions"]
        for i in action.get("test", {}).get("interactive", [])
        for s in i["script"]
        if s["name"].endswith(("-entry", "-returned"))
    ]
    failed = {
        "message": "lava-suspend-failed-3",
        "exception": "TestError",
        "error": "echo mem > /sys/power/state failed",
    }
    unsupported = {
        "message": "lava-suspend-unsupported-3",
        "exception": "TestError",
        "error": "s2idle not in /sys/power/mem_sleep",
    }
    assert [s["failures"] for s in scripts] == [[unsupported, failed], [failed]]


def test_unknown_mode_fails_generation(tmp_path, caplog):
    extra = tmp_path / "modes.yaml"
    extra.write_text("SUSPEND_MODE: mem\n")
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --dry-run-path "{tmp_path}" '
        f'--variables variables.ini "{extra}" --device-type qrb5165-rb5 '
        "--test-case suspend-resume.yaml"
    )
    assert main() == 1
    assert "SUSPEND_MODE: unknown mode 'mem'" in caplog.text
    assert not (tmp_path / "qrb5165-rb5" / "suspend-resume.yaml").exists()


def run_suspend(tmp_path, mode, mem_sleep):
    # Run the suspend command against files standing in for sysfs and procfs.
    job = render(tmp_path, mode)
    (command,) = suspend_commands(job)
    files = {
        "/sys/power/mem_sleep": mem_sleep,
        "/sys/power/state": "",
        "/proc/sys/kernel/printk": "1\t4\t1\t7\n",
    }
    for path, content in files.items():
        stand_in = tmp_path / path.replace("/", "_")
        stand_in.write_text(content)
        command = command.replace(path, str(stand_in))
    command = command.replace("sleep 5; ", "").removesuffix(" &")
    out = subprocess.run(["sh", "-c", command], capture_output=True, text=True)
    read = {p: (tmp_path / p.replace("/", "_")).read_text() for p in files}
    return out.stdout, read


def test_supported_mode_is_written(tmp_path):
    out, read = run_suspend(tmp_path, "deep", "s2idle [deep]\n")
    assert out == "lava-resumed-3\n"
    assert read["/sys/power/mem_sleep"] == "deep\n"
    assert read["/sys/power/state"] == "mem\n"
    assert read["/proc/sys/kernel/printk"] == "1\n"


def test_unsupported_mode_is_not_written(tmp_path):
    out, read = run_suspend(tmp_path, "shallow", "s2idle [deep]\n")
    assert out == "lava-suspend-unsupported-3: s2idle [deep]\n"
    assert read["/sys/power/mem_sleep"] == "s2idle [deep]\n"
    assert read["/sys/power/state"] == ""
    assert read["/proc/sys/kernel/printk"] == "1\t4\t1\t7\n"


def test_suspend_entry_reaches_the_console(tmp_path):
    # "PM: suspend entry" is an info message: the console loglevel must be
    # raised before the suspend and restored once the write returns.
    job = render(tmp_path)
    (command,) = suspend_commands(job)
    raise_level = command.index("echo 7 > /proc/sys/kernel/printk")
    suspend = command.index("echo mem > /sys/power/state")
    restore = command.index("echo $level > /proc/sys/kernel/printk")
    assert command.index("read level rest < /proc/sys/kernel/printk") < raise_level
    assert raise_level < suspend < restore < command.index("lava-resumed-")


def test_sync_before_suspend(tmp_path):
    # A long flush must end before "PM: suspend entry", or the wake can
    # come and go while the kernel still syncs after that line.
    job = render(tmp_path)
    (command,) = suspend_commands(job)
    assert command.index("sync;") < command.index("echo mem > /sys/power/state")


def test_prompt_without_boot_os_prompt(tmp_path):
    # A device without a BOOT_OS_PROMPT boots on the fallback prompt; the
    # hand-back step must wait for it as well.
    extra = tmp_path / "prompt.yaml"
    extra.write_text("BOOT_OS_PROMPT: []\n")
    sys.argv = shlex.split(
        f'lava_test_plans --dry-run --dry-run-path "{tmp_path}" '
        f'--variables variables.ini "{extra}" --device-type qrb5165-rb5 '
        "--test-case suspend-resume.yaml"
    )
    assert main() == 0
    job = YAML(typ="safe").load(open(tmp_path / "qrb5165-rb5" / "suspend-resume.yaml"))
    (shell,) = [
        i
        for action in job["actions"]
        for i in action.get("test", {}).get("interactive", [])
        if i["name"].startswith("shell-")
    ]
    assert shell["prompts"] == ["root@(.*):[/~]#"]
