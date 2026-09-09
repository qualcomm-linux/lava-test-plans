![Build Status](https://github.com/qualcomm-linux/lava-test-plans/actions/workflows/test-plans-pipeline.yml/badge.svg)
![REUSE Compliance Check](https://github.com/qualcomm-linux/lava-test-plans/actions/workflows/reuse.yml/badge.svg)

# lava-test-plans

The lava-test-plans project makes it easier to generate LAVA job definition files.
It generates the LAVA job definition file from a set of templates.

# Installation

Install lava-test-plans from this repository

    virtualenv -p python3 venv
    pip install .

If the above commands succeed, you can run to check that the program starts correctly

    lava-test-plans -h

## Developing

To install the latest development version:

    git clone https://github.com/qualcomm-linux/lava-test-plans.git
    cd ./lava-test-plans

If the above commands succeed, you can run to check that the program starts correctly

    python3 -m lava_test_plans -h

# External variables

External variables are set in the *variables.ini* file. Each line in this file
is in the form
```
key=value
```
Lines starting with *#* are omited. Variables can also be set using
*--overwrite-variables* parameter. List of used variables:

 * *PROJECT_NAME*: used as the first part in the test job name. Can be set to
   differentiate LAVA test jobs between different teams/projects
 * *BUILD_NUMBER*: used as last part in the test job name.
 * *KERNEL_BRANCH*: used in test job name
 * *OS_INFO*: used in test job name
 * *LAVA_JOB_PRIORITY*: priority of the LAVA job, used by LAVA scheduler
 * *LAVA_JOB_VISIBILITY*: defaults to *public*. This block can be used to restrict job visibility to user or group.
 * *LAVA_JOB_VISIBILITY_GROUPS*: variable should contain groups required by job. Formtatting is important and this variable should be
 formatted comma separated list. Example: group1, group2. In case of using just one group, end string with comma. Example:
 group1,
 * *AUTO_LOGIN_*: default *PROMPT='login:', *USERNAME='root' and *PASSWORD=''.
 * *BOOT_LABEL*: default BOOT_LABEL='boot'.
 * *TAGS*: variable should contain tags required by job. Formtatting is important and this variable should be
 formatted comma separated list. Example: tag1, tag2. In case of using just one tag, end string with comma. Example:
 tag1,
 * *UBOOT_VERSION_STRING*: string that is matched in the u-boot shell from output of command *version*
 * *OVERLAY_MODULES_* *: overlays modules into the rootfs.
 * *TEST_DEFINITIONS_REPOSITORY*: points to the test repository to use, default: https://github.com/Linaro/test-definitions.git

Variables can also be stored in YAML file. Usual YAML syntax applies.

## Extra job metadata

Each project template names the metadata keys it always emits - the build URL,
the pull request it came from, the workflow run that rendered it. Those are
emitted whether or not they are set, so a query written against one of them
matches every job.

Recording anything else - which recipe or commit the build came from, how it was
configured - does not need a change to the templates. *EXTRA_METADATA* is a
mapping, and every key in it is added to the metadata of the rendered job. In an
ini file it is a section, in a YAML file a nested key:

```ini
# Plain variables have to come before the section: every line after the section
# header belongs to it.
BUILD_URL=https://example.com/build/1

[EXTRA_METADATA]
kernel-recipe = "linux-qcom"
kernel-commit = "8a3c8dae4f"
kernel-config = "defconfig, distro.config"
```

```yaml
EXTRA_METADATA:
  kernel-recipe: linux-qcom
  kernel-commit: 8a3c8dae4f
```

Quote ini values: an unquoted comma is read as a list separator. Values are
rendered as strings, so a value YAML would otherwise read as something else - a
branch called *yes*, a release like *6.18* - stays what it was written as.

A key that collides with one of the named keys is ignored and the named value is
kept, rather than the key being emitted twice and the job failing to render. The
named keys are the ones queries are written against, so they win.

Unlike plain variables, which a later *--variables* file overwrites, mappings are
merged: a second file adds keys to *EXTRA_METADATA* instead of replacing it.

## Timeouts

Overall job timeout is a sum of action timeouts. There are 6 components:
 * *deploy_timeout*
 * *boot_timeout*
 * *install_fastboot_timeout*
 * *fastboot_deploy_timeout*
 * *target_deploy_timeout*
 * *TARGET_BOOT_TIMEOUT*
 * *test_timeout*

When LXC is not in use all *lxc_* timeouts are set to 0. *test_timeout* is defined for each test template. *target_* timeouts can be set separately for each device.

# GitHub action

This repository provides a reusable composite action that renders test jobs in
a GitHub workflow and returns them as a job matrix:

    - uses: qualcomm-linux/lava-test-plans@master
      with:
        machines: rb3gen2-core-kit,qcs9100-ride-sx
        distro_name: qcom-distro-6.16
        build_id: ${{ needs.build.outputs.run_id }}
        gh_token: ${{ secrets.GITHUB_TOKEN }}
        project: meta-qcom
        testplan: qcom-distro/pre-merge

See [ACTION.md](ACTION.md) for the full list of inputs and outputs.

# Repository
Pull requests are welcome to https://github.com/qualcomm-linux/lava-test-plans.
