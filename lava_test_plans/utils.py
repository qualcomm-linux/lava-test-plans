#!/usr/bin/python3
# -*- coding: utf-8 -*-
# vim: set ts=4
#
# Copyright 2023-present Linaro Limited
#
# SPDX-License-Identifier: MIT


import os
import argparse
import logging
import re
import subprocess
from configobj import ConfigObj, ConfigObjError
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


def resolve_git_revision(repository, revision=None):
    """Resolve a revision to the commit sha it points at.

    A tarball url is only cacheable while it names something immutable. A
    branch moves, and a tag can be recreated, so both are resolved to the
    commit a clone would have checked out. A sha is already immutable.
    """
    if revision and re.fullmatch(r"[0-9a-f]{40}", revision):
        return revision
    refs = [revision, "refs/tags/%s^{}" % revision] if revision else ["HEAD"]
    try:
        result = subprocess.run(
            ["git", "ls-remote", repository] + refs,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(f"Unable to resolve {revision or 'HEAD'} in {repository}: {exc}")
        return None
    if result.returncode != 0:
        logger.warning(
            f"Unable to resolve {revision or 'HEAD'} in {repository}: "
            f"{result.stderr.strip()}"
        )
        return None
    sha = None
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        # an annotated tag reports the tag object and, as ^{}, its commit
        if fields[1].endswith("^{}"):
            return fields[0]
        sha = sha or fields[0]
    if sha is None:
        logger.warning(f"{revision or 'HEAD'} does not exist in {repository}")
    return sha


def generate_audio_clips_url():

    try:
        result = subprocess.run(
            [
                "aws",
                "s3",
                "presign",
                "s3://qcom-prd-gh-artifacts/qualcomm-linux/test-media-assets/AudioClips.tar.gz",
                "--expires-in",
                "196000",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            logger.info(f"Generated audio clips URL: {url[:80]}...")
            return url
        else:
            logger.warning(f"Failed to generate audio URL: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        logger.warning("AWS CLI command timed out while generating audio URL")
        return None
    except FileNotFoundError:
        logger.warning(
            "AWS CLI not found. Install AWS CLI to enable audio clip support."
        )
        return None
    except Exception as e:
        logger.warning(f"Error generating audio URL: {e}")
        return None


def get_context(script_dirname, args_variables, args_overwrite_variables):
    context = {}
    for variables in args_variables:
        if not os.path.exists(variables):
            variables = os.path.join(script_dirname, variables)
        try:
            context.update(ConfigObj(variables).dict())
        except ConfigObjError as e:
            logger.info(e)
            logger.info("Unable to parse .ini file")
            logger.info("Trying YAML")
            with open(variables, "r") as vars_file:
                try:
                    yaml = YAML(typ="safe")
                    context.update(yaml.load(vars_file))
                except ParserError as e:
                    logger.error(e)
                except ComposerError as e:
                    logger.error(e)

    for variable in args_overwrite_variables:
        key, value = variable.split("=")
        context.update({key: value})
    return context


def validate_variables(
    script_dirname, device_type, device_path, variables, overwrite_variables
):
    context = set(get_context(script_dirname, variables, overwrite_variables).keys())
    ref_vars = os.path.join(
        os.path.abspath(os.path.join(script_dirname, device_path)),
        "variables",
        f"{device_type}.yaml",
    )
    ref_variables = set()
    with open(ref_vars, "r") as vars_file:
        yaml = YAML(typ="safe")
        ref_variables = set(yaml.load(vars_file).keys())
    var_diff = ref_variables.difference(context)
    if var_diff:
        logger.error(f"Mandatory variables missing: {var_diff}")
        return 1
    return 0


class overlay_action(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        entries = len(values)

        pairs = getattr(namespace, self.dest, [])

        if entries > 2:
            parser.error(
                f"More than 2 arguments passed for {self.dest} options. Please check help options"
            )

        if entries == 1:
            pairs.append([values[0], "/"])
        else:
            pairs.append([values[0], values[1]])
        setattr(namespace, self.dest, pairs)


COMPRESSIONS = {
    ".tar.xz": ("tar", "xz"),
    ".tar.gz": ("tar", "gz"),
    ".tgz": ("tar", "gz"),
    ".gz": (None, "gz"),
    ".xz": (None, "xz"),
    ".zst": (None, "zstd"),
    ".py": ("file", None),
    ".sh": ("file", None),
}


def compression(path):
    for ext, ret in COMPRESSIONS.items():
        if path.endswith(ext):
            return ret
    return (None, None)
