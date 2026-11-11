#!/usr/bin/env python3
#
# Copyright 2026 Qualcomm Technologies, Inc.
#
# SPDX-License-Identifier: MIT
"""Work out the builds submit-jobs.yml renders test jobs for.

For every build in .github/lava-submit.yml, find the latest scheduled run of
the workflow that made it and print, for each of its test plans, the inputs
of one lava-test-plans action call: the build URL the images are downloaded
from and the variables the jobs are rendered with. The machines and the test
plans are taken from the configuration as they are.

meta-qcom
    The latest run that published build URLs for the distro. The action
    derives the image URL of each machine from the build URL and the distro.

qcom-deb-images
    The latest run in which the images of every tested suite were uploaded.
    The image file name is selected with DEBIAN_RELEASE and ARTIFACT_PREFIX.

The GitHub API is read with the token in GH_TOKEN (or GITHUB_TOKEN).
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
SERVER = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
# how many of the latest runs of a workflow are looked at for a usable build
RUNS_TO_CHECK = 10


def warning(message):
    print(f"::warning::{message}", file=sys.stderr)


def notice(message):
    print(message, file=sys.stderr)


def api(path, params=None):
    url = f"{API}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # the API answers a slow listing with a gateway error now and then
            if error.code < 500 or attempt == 3:
                raise
            notice(f"{url}: {error}, retrying")
            time.sleep(10 * attempt)


def api_list(path, key, params=None):
    """Every item of a paginated list endpoint."""
    params = dict(params or {}, per_page=100)
    page = 1
    while True:
        items = api(path, dict(params, page=page))[key]
        yield from items
        if len(items) < 100:
            return
        page += 1


def latest_runs(repository, workflow, branch):
    """The latest finished scheduled runs of a workflow on a branch."""
    return api(
        f"repos/{repository}/actions/workflows/{workflow}/runs",
        {
            "branch": branch,
            "event": "schedule",
            "status": "completed",
            "per_page": RUNS_TO_CHECK,
        },
    )["workflow_runs"]


def variables(config, extra, metadata):
    """The variables input of the action.

    The EXTRA_METADATA section header ends the plain variables, so the
    metadata goes last.
    """
    lines = config.get("variables", "").splitlines() + extra
    lines.append("[EXTRA_METADATA]")
    lines += [f"{key} = {json.dumps(value)}" for key, value in metadata.items()]
    return "\n".join(lines) + "\n"


def run_metadata(repository, run):
    return {
        "build-type": "NIGHTLY",
        "build-run-id": str(run["id"]),
        "build-run-url": run["html_url"],
        "source-repo": f"{SERVER}/{repository}",
        "source-branch": run["head_branch"],
        "source-sha": run["head_sha"],
    }


def plan_meta_qcom(config, common):
    project = "meta-qcom"
    repository = config["repository"]
    runs = latest_runs(repository, config["workflow"], config["branch"])
    # build URL artifact names of each run, read once
    published = {}
    entries = []
    for build in config["builds"]:
        distro = build["distro"]
        run = None
        for candidate in runs:
            if candidate["id"] not in published:
                published[candidate["id"]] = {
                    artifact["name"]
                    for artifact in api_list(
                        f"repos/{repository}/actions/runs/{candidate['id']}/artifacts",
                        "artifacts",
                    )
                    if not artifact["expired"]
                }
            if any(
                name.startswith("build-url_") and name.endswith(f"_{distro}")
                for name in published[candidate["id"]]
            ):
                run = candidate
                break
        if run is None:
            warning(f"{project}: no {config['workflow']} run with {distro} builds")
            continue
        notice(f"{project}: {distro} using {run['html_url']} ({run['head_sha']})")
        url = config["artifacts_url"].format(
            run_id=run["id"], run_attempt=run["run_attempt"]
        )
        for testplan, machines in build["testplans"].items():
            entries.append(
                {
                    "name": f"{project}-{testplan}",
                    "project": project,
                    "testplan": testplan,
                    "machines": ",".join(machines),
                    "distro_name": distro,
                    "build_url": url,
                    "os_info": config.get("os_info", ""),
                    "variables": variables(
                        config,
                        [],
                        dict(
                            common,
                            **run_metadata(repository, run),
                            distro=distro,
                            testplan=testplan,
                            machine="%MACHINE%",
                        ),
                    ),
                }
            )
    return entries


def suite_job(jobs, suite, variant):
    # build.yml names its jobs "build (<suite>, <variant>, <profile>)", the
    # others "build (<suite>)" or "build / build-images (<suite>)"; only the
    # default profile is tested
    pattern = re.compile(
        rf"\({re.escape(suite)}(, {re.escape(variant)}, default)?\) / Build and upload images$"
    )
    for job in jobs:
        if pattern.search(job["name"]):
            return job
    return None


def plan_qcom_deb_images(config, common):
    project = "qcom-deb-images"
    repository = config["repository"]
    entries = []
    for build in config["builds"]:
        kernel = build["kernel"]
        variant = build.get("variant", "console")
        suites = build["suites"]
        run = None
        attempts = {}
        for candidate in latest_runs(repository, build["workflow"], config["branch"]):
            jobs = list(
                api_list(
                    f"repos/{repository}/actions/runs/{candidate['id']}/jobs",
                    "jobs",
                    {"filter": "latest"},
                )
            )
            found = {suite: suite_job(jobs, suite, variant) for suite in suites}
            if all(job and job["conclusion"] == "success" for job in found.values()):
                run = candidate
                # a re-run job uploads under the attempt it ran in
                attempts = {suite: job["run_attempt"] for suite, job in found.items()}
                break
            notice(
                f"{project}: {kernel} images were not all built in {candidate['html_url']}"
            )
        if run is None:
            warning(f"{project}: no {build['workflow']} run built every {kernel} image")
            continue
        notice(f"{project}: {kernel} using {run['html_url']} ({run['head_sha']})")

        for suite in suites:
            artifact_prefix = suite if variant == "console" else f"{suite}-{variant}"
            url = config["artifacts_url"].format(
                run_id=run["id"], run_attempt=attempts[suite]
            )
            for testplan, machines in build["testplans"].items():
                entries.append(
                    {
                        "name": f"{project}-{kernel}-{artifact_prefix}-{testplan}",
                        "project": project,
                        "testplan": testplan,
                        "machines": ",".join(machines),
                        "distro_name": "",
                        "build_url": url,
                        "os_info": config.get("os_info", ""),
                        "variables": variables(
                            config,
                            [
                                f"DEBIAN_RELEASE={suite}",
                                f"ARTIFACT_PREFIX={artifact_prefix}",
                            ],
                            dict(
                                common,
                                **run_metadata(repository, run),
                                distro="debian",
                                suite=suite,
                                variant=variant,
                                kernel=kernel,
                                testplan=testplan,
                                machine="%MACHINE%",
                            ),
                        ),
                    }
                )
    return entries


PROJECTS = {
    "meta-qcom": plan_meta_qcom,
    "qcom-deb-images": plan_qcom_deb_images,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=".github/lava-submit.yml")
    parser.add_argument("--testkit-ref", required=True)
    parser.add_argument("--lava-test-plans-ref", required=True)
    parser.add_argument(
        "--projects",
        default="",
        help="comma separated projects to plan for; all configured ones when empty",
    )
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)
    wanted = [p.strip() for p in args.projects.split(",") if p.strip()] or list(config)
    common = {
        "testkit-ref": args.testkit_ref,
        "lava-test-plans-ref": args.lava_test_plans_ref,
        "gh-workflow-name": os.environ.get("GITHUB_WORKFLOW", ""),
    }

    entries = []
    for project in wanted:
        if project not in config or project not in PROJECTS:
            sys.exit(f"unknown project {project}")
        try:
            entries += PROJECTS[project](config[project], common)
        except urllib.error.HTTPError as error:
            sys.exit(f"{project}: {error.url}: {error}")

    for entry in entries:
        entry["name"] = re.sub(r"[^A-Za-z0-9._-]+", "-", entry["name"])
    json.dump({"include": entries}, sys.stdout)
    print()


if __name__ == "__main__":
    main()
