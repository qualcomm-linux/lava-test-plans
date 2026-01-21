#!/usr/bin/python3
# -*- coding: utf-8 -*-
# vim: set ts=4
#
# Copyright 2023-present Linaro Limited
#
# SPDX-License-Identifier: MIT

import pytest
import subprocess
from unittest.mock import patch, MagicMock, mock_open
from lava_test_plans.utils import (
    generate_audio_clips_url,
    get_context,
    validate_variables,
    overlay_action,
    compression,
)
import argparse
import os
import tempfile


class TestGenerateAudioClipsUrl:
    """Test cases for generate_audio_clips_url function"""

    @patch("lava_test_plans.utils.subprocess.run")
    def test_generate_audio_clips_url_success(self, mock_run):
        """Test successful URL generation"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://s3.amazonaws.com/test-url?signature=abc123\n"
        mock_run.return_value = mock_result

        url = generate_audio_clips_url()

        assert url == "https://s3.amazonaws.com/test-url?signature=abc123"
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][0] == "aws"
        assert call_args[0][0][1] == "s3"
        assert call_args[0][0][2] == "presign"

    @patch("lava_test_plans.utils.subprocess.run")
    def test_generate_audio_clips_url_failure(self, mock_run):
        """Test URL generation failure"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: Invalid credentials"
        mock_run.return_value = mock_result

        url = generate_audio_clips_url()

        assert url is None

    @patch("lava_test_plans.utils.subprocess.run")
    def test_generate_audio_clips_url_timeout(self, mock_run):
        """Test URL generation timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aws", timeout=30)

        url = generate_audio_clips_url()

        assert url is None

    @patch("lava_test_plans.utils.subprocess.run")
    def test_generate_audio_clips_url_aws_not_found(self, mock_run):
        """Test when AWS CLI is not installed"""
        mock_run.side_effect = FileNotFoundError()

        url = generate_audio_clips_url()

        assert url is None

    @patch("lava_test_plans.utils.subprocess.run")
    def test_generate_audio_clips_url_generic_exception(self, mock_run):
        """Test generic exception handling"""
        mock_run.side_effect = Exception("Unexpected error")

        url = generate_audio_clips_url()

        assert url is None


class TestGetContext:
    """Test cases for get_context function"""

    def test_get_context_with_ini_file(self):
        """Test get_context with INI file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write("[section]\n")
            f.write("key1 = value1\n")
            f.write("key2 = value2\n")
            temp_file = f.name

        try:
            context = get_context(os.path.dirname(temp_file), [temp_file], [])
            # ConfigObj returns nested dict with section names
            assert "section" in context
            assert context["section"]["key1"] == "value1"
            assert context["section"]["key2"] == "value2"
        finally:
            os.unlink(temp_file)

    def test_get_context_with_yaml_file(self):
        """Test get_context with YAML file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key1: value1\n")
            f.write("key2: value2\n")
            temp_file = f.name

        try:
            context = get_context(os.path.dirname(temp_file), [temp_file], [])
            assert "key1" in context
            assert context["key1"] == "value1"
            assert "key2" in context
            assert context["key2"] == "value2"
        finally:
            os.unlink(temp_file)

    def test_get_context_with_overwrite_variables(self):
        """Test get_context with overwrite variables"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write("[section]\n")
            f.write("key1 = value1\n")
            temp_file = f.name

        try:
            context = get_context(
                os.path.dirname(temp_file), [temp_file], ["key1=overwritten"]
            )
            assert context["key1"] == "overwritten"
        finally:
            os.unlink(temp_file)


class TestValidateVariables:
    """Test cases for validate_variables function"""

    def test_validate_variables_missing(self):
        """Test validate_variables with missing variables"""
        # Create temporary files for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create variables file
            var_file = os.path.join(tmpdir, "variables.ini")
            with open(var_file, "w") as f:
                f.write("[section]\n")
                f.write("key1 = value1\n")

            # Create device path and reference variables
            device_path = tmpdir
            variables_dir = os.path.join(device_path, "variables")
            os.makedirs(variables_dir, exist_ok=True)

            ref_var_file = os.path.join(variables_dir, "test-device.yaml")
            with open(ref_var_file, "w") as f:
                f.write("key1: value1\n")
                f.write("key2: value2\n")  # This key is missing

            result = validate_variables(
                tmpdir, "test-device", device_path, [var_file], []
            )
            assert result == 1  # Should return 1 for missing variables

    def test_validate_variables_all_present(self):
        """Test validate_variables with all variables present"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create variables file with YAML format (no sections)
            var_file = os.path.join(tmpdir, "variables.yaml")
            with open(var_file, "w") as f:
                f.write("key1: value1\n")
                f.write("key2: value2\n")

            # Create device path and reference variables
            device_path = tmpdir
            variables_dir = os.path.join(device_path, "variables")
            os.makedirs(variables_dir, exist_ok=True)

            ref_var_file = os.path.join(variables_dir, "test-device.yaml")
            with open(ref_var_file, "w") as f:
                f.write("key1: value1\n")
                f.write("key2: value2\n")

            result = validate_variables(
                tmpdir, "test-device", device_path, [var_file], []
            )
            assert result == 0  # Should return 0 for all variables present


class TestOverlayAction:
    """Test cases for overlay_action class"""

    def test_overlay_action_single_argument(self):
        """Test overlay_action with single argument"""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--overlay",
            action=overlay_action,
            nargs="+",
            dest="overlays",
            default=[],
        )

        args = parser.parse_args(["--overlay", "http://example.com/overlay.tar.gz"])
        assert len(args.overlays) == 1
        assert args.overlays[0] == ["http://example.com/overlay.tar.gz", "/"]

    def test_overlay_action_two_arguments(self):
        """Test overlay_action with two arguments"""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--overlay",
            action=overlay_action,
            nargs="+",
            dest="overlays",
            default=[],
        )

        args = parser.parse_args(
            ["--overlay", "http://example.com/overlay.tar.gz", "/custom/path"]
        )
        assert len(args.overlays) == 1
        assert args.overlays[0] == ["http://example.com/overlay.tar.gz", "/custom/path"]

    def test_overlay_action_multiple_overlays(self):
        """Test overlay_action with multiple overlays"""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--overlay",
            action=overlay_action,
            nargs="+",
            dest="overlays",
            default=[],
        )

        args = parser.parse_args(
            [
                "--overlay",
                "http://example.com/overlay1.tar.gz",
                "--overlay",
                "http://example.com/overlay2.tar.gz",
                "/path",
            ]
        )
        assert len(args.overlays) == 2
        assert args.overlays[0] == ["http://example.com/overlay1.tar.gz", "/"]
        assert args.overlays[1] == ["http://example.com/overlay2.tar.gz", "/path"]


class TestCompression:
    """Test cases for compression function"""

    def test_compression_tar_xz(self):
        """Test compression detection for .tar.xz files"""
        assert compression("file.tar.xz") == ("tar", "xz")

    def test_compression_tar_gz(self):
        """Test compression detection for .tar.gz files"""
        assert compression("file.tar.gz") == ("tar", "gz")

    def test_compression_tgz(self):
        """Test compression detection for .tgz files"""
        assert compression("file.tgz") == ("tar", "gz")

    def test_compression_gz(self):
        """Test compression detection for .gz files"""
        assert compression("file.gz") == (None, "gz")

    def test_compression_xz(self):
        """Test compression detection for .xz files"""
        assert compression("file.xz") == (None, "xz")

    def test_compression_zst(self):
        """Test compression detection for .zst files"""
        assert compression("file.zst") == (None, "zstd")

    def test_compression_py(self):
        """Test compression detection for .py files"""
        assert compression("file.py") == ("file", None)

    def test_compression_sh(self):
        """Test compression detection for .sh files"""
        assert compression("file.sh") == ("file", None)

    def test_compression_unknown(self):
        """Test compression detection for unknown file types"""
        assert compression("file.unknown") == (None, None)
