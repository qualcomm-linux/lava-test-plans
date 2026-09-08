#!/usr/bin/python3
# -*- coding: utf-8 -*-
# vim: set ts=4
#
# Copyright 2026 Qualcomm Technologies, Inc.
#
# Author: Matt Hart <matthart@qti.qualcomm.com>
#
# SPDX-License-Identifier: MIT

import glob
import io
import os
import shlex
import sys
import tarfile
import urllib.request
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML

from lava_test_plans.__main__ import main

DEVICE = "rb3gen2-core-kit"
DEVICE_PATH = "lava_test_plans/projects/meta-qcom/devices"
VARIABLES = "projects/meta-qcom/variables.yaml"
TESTCASE = "pre-merge-basic.yaml"

GITHUB_REPO = "https://github.com/qualcomm-linux/qcom-linux-testkit/"
TAG = "testkit-2026.08.14"
# the commit refs/tags/<TAG>^{} points at, i.e. what a clone checks out
TAG_SHA = "010afe5f667c8f876d450c856996ba09aa0353b9"
ARCHIVE_URL = (
    "https://github.com/qualcomm-linux/qcom-linux-testkit/archive/%s.tar.gz" % TAG_SHA
)


def render(dry_run_path, repository, revision=None):
    """Render one testcase, returning its definitions and the raw job text."""
    overwrite = []
    if repository is not None:
        overwrite.append("TEST_DEFINITIONS_REPOSITORY=%s" % repository)
    if revision is not None:
        overwrite.append("TEST_DEFINITIONS_REVISION=%s" % revision)
    argv = (
        'lava_test_plans --dry-run --dry-run-path "%s" --variables "%s"'
        ' --testplan-device-path "%s" --device-type "%s" --test-case "%s"'
        % (dry_run_path, VARIABLES, DEVICE_PATH, DEVICE, TESTCASE)
    )
    if overwrite:
        # --overwrite-variables takes every pair in a single flag
        argv += " --overwrite-variables " + " ".join(overwrite)
    sys.argv = shlex.split(argv)
    assert main() == 0

    rendered = glob.glob(
        os.path.join(str(dry_run_path), "**", "*.yaml"), recursive=True
    )
    assert len(rendered) == 1
    with open(rendered[0]) as rendered_job:
        text = rendered_job.read()
    job = YAML(typ="safe").load(text)
    definition_lists = [a["test"]["definitions"] for a in job["actions"] if "test" in a]
    assert len(definition_lists) == 1
    assert len(definition_lists[0]) > 1
    return definition_lists[0], text


@pytest.mark.parametrize(
    "repository,resolvable,expected",
    [
        # github.com over http(s) is the only layout we know how to build
        ("https://github.com/qualcomm-linux/qcom-linux-testkit/", True, "url"),
        ("https://github.com/qualcomm-linux/qcom-linux-testkit.git", True, "url"),
        ("http://github.com/org/repo", True, "url"),
        # a self hosted server whose name merely contains github.com
        ("https://mygithub.com/org/repo", False, "git"),
        ("https://git.github.com.corp.net/org/repo", False, "git"),
        # github enterprise is a different host, so assume nothing about it
        ("https://github.corp.internal/org/repo", False, "git"),
        # servers with their own layout, or with no http access at all
        ("https://git.internal.example/team/tests.git", False, "git"),
        ("https://gitlab.com/org/repo.git", False, "git"),
        ("git@github.com:org/repo.git", False, "git"),
        ("git://git.kernel.org/pub/scm/x/y.git", False, "git"),
    ],
)
def test_definition_source_by_repository(tmp_path, repository, resolvable, expected):
    with patch(
        "lava_test_plans.__main__.resolve_git_revision", return_value=TAG_SHA
    ) as resolve:
        definitions, _ = render(tmp_path, repository, TAG)
    assert resolve.called is resolvable
    assert {d["from"] for d in definitions} == {expected}


@patch("lava_test_plans.__main__.resolve_git_revision", return_value=TAG_SHA)
def test_revision_is_replaced_by_its_sha(resolve, tmp_path):
    """A tag can be recreated, so the url must name the commit, not the tag."""
    definitions, _ = render(tmp_path, GITHUB_REPO, TAG)
    assert resolve.call_args[0][:2] == (GITHUB_REPO, TAG)
    assert {d["repository"] for d in definitions} == {ARCHIVE_URL}
    assert all(d["strip-components"] == 1 for d in definitions)
    assert not any("revision" in d for d in definitions)


@patch("lava_test_plans.__main__.resolve_git_revision", return_value=TAG_SHA)
def test_unpinned_revision_is_resolved(resolve, tmp_path):
    """With no revision the default branch head is pinned instead."""
    definitions, _ = render(tmp_path, GITHUB_REPO, "")
    assert resolve.call_args[0][0] == GITHUB_REPO
    assert {d["from"] for d in definitions} == {"url"}
    assert {d["repository"] for d in definitions} == {ARCHIVE_URL}


@patch("lava_test_plans.__main__.resolve_git_revision", return_value=None)
def test_unresolvable_revision_falls_back_to_git(resolve, tmp_path):
    """Rendering must not depend on reaching the remote."""
    definitions, _ = render(tmp_path, GITHUB_REPO, TAG)
    assert resolve.called
    assert {d["from"] for d in definitions} == {"git"}
    assert {d["revision"] for d in definitions} == {TAG}


@patch("lava_test_plans.__main__.resolve_git_revision", return_value=TAG_SHA)
def test_job_records_what_the_revision_resolved_to(resolve, tmp_path):
    """The job has to say which commit it actually tested."""
    _, text = render(tmp_path, GITHUB_REPO, TAG)
    assert "# %s resolved to %s" % (TAG, TAG_SHA) in text


@patch("lava_test_plans.__main__.resolve_git_revision", return_value=TAG_SHA)
def test_job_records_head_when_no_revision_was_asked_for(resolve, tmp_path):
    _, text = render(tmp_path, GITHUB_REPO, "")
    assert "# HEAD resolved to %s" % TAG_SHA in text


@pytest.mark.skipif(
    bool(os.getenv("SKIP_NETWORK_TESTS")), reason="SKIP_NETWORK_TESTS is set"
)
def test_tarball_url_resolves(tmp_path):
    """The generated url must be fetchable, and hold what the job asks for.

    strip-components: 1 is only correct while the archive has a single root
    directory, so check that and the paths together against the real tarball.
    This also proves the annotated tag resolved to the commit it points at.
    """
    definitions, _ = render(tmp_path, GITHUB_REPO, TAG)
    url = definitions[0]["repository"]
    assert url == ARCHIVE_URL

    with urllib.request.urlopen(url, timeout=60) as response:
        assert response.status == 200
        archive = io.BytesIO(response.read())

    with tarfile.open(fileobj=archive, mode="r:gz") as tarball:
        names = tarball.getnames()

    roots = {name.split("/")[0] for name in names}
    assert len(roots) == 1, "strip-components: 1 needs a single root directory"
    root = roots.pop()
    stripped = {name[len(root) + 1 :] for name in names}

    for definition in definitions:
        assert definition["path"] in stripped
