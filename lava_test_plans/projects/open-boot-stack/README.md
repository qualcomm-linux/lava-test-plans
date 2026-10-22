# open-boot-stack LAVA test plans

## Brief

Test plans for an open source boot stack on Qualcomm boards: TF-A (BL2 or
U-Boot SPL, BL31), OP-TEE and U-Boot in place of the vendor firmware, booting
a Linux UKI with an initramfs. Every component of a build carries the same
build fingerprint, so a job first proves that the board runs the build under
test, then checks what the firmware hands over to Linux and the platform
features that depend on it (CPUs and PSCI, cpufreq, CPU features, remote
processors, FastRPC, machine learning inference on the CPU, GPU and NPU,
audio, GPU, video, KVM, OP-TEE).

The test definitions are the generic ones in
[test-definitions](https://github.com/Linaro/test-definitions)
`automated/linux/` (boot-fingerprint, boot-handoff, cpu-features,
cpufreq-policy, remoteproc-smoke, which also restarts the remote
processors, fastrpc, inference, alsa-dsp-restart, optee, smoke, which
runs the GPU render check, video-codec, kvm-unit-tests, kvm-guest,
cpu-hotplug, kernel-health, maxcpus, memtest).

## Devices

| Machine | LAVA device type | Base device |
|---|---|---|
| `ventuno-q` | `monaco-arduino-monza` | `devices/monaco-arduino-monza` |
| `uno-q` | `qrb2210-arduino-imola` | `devices/qrb2210-arduino-imola` |
| `rb3gen2` | `qcs6490-rb3gen2` | `devices/qcs6490-rb3gen2` |
| `qcs615-ride` | `qcs615-ride` | `devices/qcs615-ride` |
| `lemans-evk` | `lemans-evk` | `devices/lemans-evk` |

A device file names the qcomflash layout, the firmware stages whose console
banners carry the fingerprint (`firmware_stages`) and the tests the board
cannot run (`EXCLUDED_TESTS`). What the tests expect of
the board (CPU count, boot CPU, KVM mode, PSCI mode, remote processors, audio
and video parameters, CPU features, inference processing units) is in
`boards/<machine>.yaml`, a variables file passed after `variables.yaml`, so
that the test cases can use it.

The images boot Linux from an initramfs; the `rootfs` partition of the
qcomflash only carries the LAVA overlay, which the login mounts.

## Test plans

| Test plan | Jobs |
|---|---|
| `open-boot-stack/full` | `open-boot-stack`: cold boot fingerprints, the Linux tests, a warm reboot with fingerprints and the boot checks again. |
| `open-boot-stack/maxcpus` | An image booting with `maxcpus=MAXCPUS`: the CPUs started late through PSCI CPU_ON. |
| `open-boot-stack/memtest` | An image booting with `memtest=MEMTEST`: the kernel's early memory test. |
| `open-boot-stack/negative` | `open-boot-stack-inference-negative`: the inference test with the NSP/DSP remoteprocs stopped, no OpenCL platform, and the expected classes rotated; the affected cases must fail. |

## Variables

| Variable | |
|---|---|
| `ROOTFS_URL` | The qcomflash tarball. |
| `AUTH_HEADER_NAME`, `AUTH_HEADER_TOKEN` | Header for downloading it, if needed. |
| `FIRMWARE_FINGERPRINT` | The build fingerprint every firmware stage prints. |
| `STAGE_FINGERPRINTS` | A mapping of stage banner to fingerprint, for stages taken from another build. |
| `LINUX_FINGERPRINT`, `ROOTFS_FINGERPRINT` | When the kernel or the rootfs come from another build. |
| `MAXCPUS`, `MEMTEST` | The values the maxcpus and memtest images boot with. |
| `QAIRT_URL`, `QAIRT_SHA256`, `QAIRT_ROOT` | The Qualcomm AI Runtime SDK zip, downloaded by the dispatcher as a file overlay on the rootfs partition for boards with a QNN entry; it is never part of an image. |
| `INFERENCE_MODEL_DIR` | The model bundle in the image, or `INFERENCE_MODEL_URL`: a tarball of `model/`, deployed as an overlay. |

## Testing

Render the jobs without submitting them:

```sh
python3 -m lava_test_plans \
    --variables projects/open-boot-stack/variables.yaml \
                projects/open-boot-stack/boards/ventuno-q.yaml \
    --testplan-device-path projects/open-boot-stack/devices \
    --device-type ventuno-q \
    --test-plan open-boot-stack/full \
    --dry-run
```

Add a variables file with the build's `ROOTFS_URL` and fingerprints to
produce a submittable job; for the maxcpus and memtest plans, pass the
`MAXCPUS` or `MEMTEST` value as well.
