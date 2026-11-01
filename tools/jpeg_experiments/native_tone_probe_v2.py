"""Reproduce original ARM Image Control tone curves; save read-only evidence.

Run with a Python environment containing Unicorn and the existing GR3x probe
dependencies. This uses the repository's bounded native-function harness, not
a physical ISP, complete camera emulator, or JPEG encoder. It does NOT probe
the separate D-Range Highlight Correction / Shadow Correction processing.

Example from the repository root (PowerShell; choose an output directory):
  & research/camera-ui/venv/Scripts/python.exe `
    tools/jpeg_experiments/native_tone_probe_v2.py `
    --rtos research/camera-ui/evidence/gr3x-160-rtos.bin `
           research/camera-ui/hardware-prep/gr3-210-rtos.bin `
    --base research/camera-ui/evidence/adj-base-manifest.json `
    --out-dir path/to/evidence

The named JSON and text reports must not already exist. Inputs are only read;
the probe's native-code patches and synthetic state exist in emulator RAM.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys


REPO = Path(__file__).resolve().parents[2]
FUNCTION = 0x536E84C8
FUNCTION_END = 0x536E8BE0
CONTROL_OFFSETS = {"key": 2, "contrast": 3, "highlight": 4, "shadow": 5}
SAMPLE_INDICES = (0, 4, 16, 46, 128, 192, 255)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def probe(rtos_paths: list[Path], base_path: Path) -> dict:
    """Run each accepted original RTOS, retaining every actual curve sample."""
    if not __debug__:
        raise RuntimeError("Run without Python -O; native harness assertions must stay enabled")
    sys.path.insert(0, str(REPO / "tools/gr3x"))
    import unicorn
    from image_control_probe import LookProbe
    from image_controls_verify import descriptor
    from color_curve_probe import ISP
    from native_probe import BASE, OUTPUT
    from adj_probe import put
    from identity import by_rtos

    base_path = base_path.resolve(strict=True)
    manifest_bytes = base_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    reference_source = (REPO / "core/src/color/gr3x-camera.ts").read_text(encoding="utf-8")
    match = re.search(r"GR3X_REFERENCE_CURVE = new Uint16Array\(\[([\s\d,]+)\]\)", reference_source)
    if not match:
        raise ValueError("Cannot find the independent Standard reference curve")
    reference = tuple(int(value) for value in match[1].split(",") if value.strip())
    if len(reference) != 256:
        raise ValueError("The independent Standard reference must have 256 entries")

    profiles = []
    for supplied in rtos_paths:
        path = supplied.resolve(strict=True)
        data = path.read_bytes()
        identity = by_rtos(data)  # refuses every RTOS except the exact known builds
        emulator = LookProbe(data, manifest)
        cpu = emulator.uc
        # The harness uses an ADJ/geometry patch manifest. Independently guard
        # the complete curve-function region so these outputs use original code.
        original_function = data[FUNCTION - BASE:FUNCTION_END - BASE]
        if bytes(cpu.mem_read(FUNCTION, FUNCTION_END - FUNCTION)) != original_function:
            raise ValueError("The harness changed the original native curve function")
        rows = []
        for control, offset in CONTROL_OFFSETS.items():
            for user_value in range(-4, 5):
                parameters = [4] * 26
                parameters[offset] = user_value + 4
                descriptor(emulator, 11, parameters)
                put(cpu, OUTPUT + 0x64, 8192)
                cpu.mem_write(ISP - 32, b"\xa5" * (0x3400 + 64))
                cpu.mem_write(ISP, bytes(0x3400))
                emulator.call(FUNCTION, ISP, OUTPUT)
                packed = bytes(cpu.mem_read(ISP, 512))
                curve = struct.unpack("<256H", packed)
                if cpu.mem_read(ISP - 32, 32) != b"\xa5" * 32 or cpu.mem_read(ISP + 0x3400, 32) != b"\xa5" * 32:
                    raise AssertionError("Native curve generation changed a buffer canary")
                if any(value > 16384 for value in curve) or any(b < a for a, b in zip(curve, curve[1:])):
                    raise AssertionError("Native curve was not bounded and monotone")
                if user_value == 0 and curve != reference:
                    raise AssertionError("Native neutral curve differs from the independent repository reference")
                rows.append({
                    "control": control,
                    "user_value": user_value,
                    "stored_byte_value": user_value + 4,
                    "common_property_byte_offset": f"0x{0x77d + offset:x}",
                    "all_other_image_control_parameter_bytes": 4,
                    "samples_at_report_indices": [curve[index] for index in SAMPLE_INDICES],
                    "black_endpoint": curve[0],
                    "last_sample": curve[-1],
                    "first_index_at_native_white": next((i for i, value in enumerate(curve) if value >= 16383), None),
                    "monotone": True,
                    "curve_sha256_uint16_le": _sha(packed),
                    "curve_uint16": list(curve),
                })
        # Input immutability is checked independently of the emulator's memory.
        if _sha(path.read_bytes()) != identity["rtos_sha256"]:
            raise AssertionError("The RTOS input changed during the probe")
        profiles.append({
            "source_path": str(path),
            "camera": identity["camera"],
            "profile_id": identity["id"],
            "rtos_sha256": identity["rtos_sha256"],
            "rtos_size_bytes": len(data),
            "original_native_curve_function_region_unchanged": True,
            "neutral_matches_all_256_independent_reference_samples": True,
            "case_count": len(rows),
            "cases": rows,
        })

    same_profiles = None
    if len(profiles) > 1:
        expected = [row["curve_sha256_uint16_le"] for row in profiles[0]["cases"]]
        same_profiles = all([row["curve_sha256_uint16_le"] for row in item["cases"]] == expected for item in profiles[1:])
        if not same_profiles:
            raise AssertionError("The supplied original RTOS profiles generated different curves")
    all_rows = [row for item in profiles for row in item["cases"]]
    return {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "native Image Control tone sliders, one control varied at a time",
        "native_curve_function": f"0x{FUNCTION:x}",
        "native_descriptor_function": "0x536dc0f4",
        "look": {"name": "Standard", "native_id": 11},
        "descriptor_scale_at_0x64": 8192,
        "sample_indices": list(SAMPLE_INDICES),
        "input_sampling_convention": "camera base-curve model: input i/256; not a calibration to LibRaw scene-linear sRGB",
        "output_units": "native unsigned 16-bit samples; nominal white 16383, native white endpoint includes 16384",
        "runtime": {"python": sys.version, "unicorn": unicorn.__version__},
        "base_manifest": {"path": str(base_path), "sha256": _sha(manifest_bytes), "scope": "existing ADJ/geometry probe harness; original curve-function region independently checked unchanged"},
        "profiles": profiles,
        "all_supplied_profiles_produce_identical_curves": same_profiles,
        "measured": {
            "cases": len(all_rows),
            "all_curves_monotone": all(row["monotone"] for row in all_rows),
            "all_black_endpoints_zero": all(row["black_endpoint"] == 0 for row in all_rows),
            "all_last_samples_16384": all(row["last_sample"] == 16384 for row in all_rows),
        },
        "automatic_corrections": {
            "tested": False,
            "image_control_highlight_shadow_are_separate_controls": True,
            "evidence_supports_automatic_highlight_shadow_correction_algorithm_claims": False,
            "explanation": "Only Image Control Key/Contrast/Highlight/Shadow bytes COMMON+0x77f through +0x782 are varied. D-Range Highlight Correction and Shadow Correction settings, image-dependent automatic decisions, sensor exposure changes and correction pixel-processing functions are not exercised.",
            "repository_menu_evidence_only": ["core/src/fw/gr3x/datestamp.ts: D-Range Correction submenu record 6 and controller ID 0x020000ba are reused as menu templates", "tools/gr3x/datestamp_probe.py: verifies D-Range menu records/factory mappings; not the correction image-processing algorithm"],
        },
        "interpretation": [
            "For the tested Standard setup, Shadow moves dark curve samples while leaving true black at zero; Highlight moves upper tones while retaining the white endpoint.",
            "Contrast changes dark and upper tones together; Key shifts the overall distribution. These results cover independent -4..+4 slider sweeps, not every combination or every native style.",
            "The new fade curve's nonzero black endpoint and lowered asymptotic white are additional creative curve choices, not effects proven to come from the Image Control Shadow slider.",
            "Existing independent RGB curve tables can represent raised black or lowered white endpoints. A post-curve table cannot recover scene distinctions already clipped before that table.",
        ],
        "limits": [
            "Bounded original ARM function execution with synthetic RAM and existing singleton/service substitutes; no complete camera boot or physical ISP is executed.",
            "No physical JPEG output, RAW capture exposure, sensor clipping, spatial processing, scene-adaptive processing or automatic Highlight/Shadow Correction is verified.",
            "Do not infer automatic D-Range behavior, highlight recovery or physical-camera fidelity from these Image Control curves.",
            "Firmware sources and user photographs are not modified; no firmware update is generated.",
        ],
    }


def report_text(report: dict) -> str:
    lines = [
        "Native Ricoh Image Control tone-curve evidence",
        "",
        "These are Image Control Key, Contrast, Highlight and Shadow sliders.",
        "They are NOT the separate D-Range Highlight Correction / Shadow Correction processing.",
        "No automatic-correction algorithm claim is supported by this probe.",
        "",
        f"Generated UTC: {report['generated_utc']}",
        f"Original curve function: {report['native_curve_function']}",
        f"Descriptor function: {report['native_descriptor_function']}",
        "Look: Standard (11); descriptor scale at +0x64 = 8192.",
        "Each slider is swept -4..+4 while the other Image Control bytes stay neutral (stored 4).",
        "Full 256-entry native outputs and hashes for every case are in native-tone-controls.json.",
        "Input i/256 is the camera base-curve model convention, not a LibRaw scene calibration.",
        "Output samples below are native integers; nominal white 16383, native endpoint 16384.",
        "",
    ]
    for profile in report["profiles"]:
        lines.extend([
            f"Camera/build: {profile['camera']} / {profile['profile_id']}",
            f"RTOS: {profile['source_path']}",
            f"SHA-256: {profile['rtos_sha256']}",
            "Original curve-function region unchanged in emulator RAM; all 256 neutral samples match the independent repository reference.",
            "",
            "Control      Value   i=0     i=4    i=16    i=46   i=128   i=192   i=255  first white",
        ])
        for row in profile["cases"]:
            values = " ".join(f"{value:7d}" for value in row["samples_at_report_indices"])
            lines.append(f"{row['control']:12s}{row['user_value']:+4d} {values} {row['first_index_at_native_white']:8d}")
        lines.append("")
    lines.extend([
        f"Supplied builds have identical complete curves: {report['all_supplied_profiles_produce_identical_curves']}",
        f"Measured summary: {json.dumps(report['measured'], sort_keys=True)}",
        "",
        "Interpretation:",
        *[f"- {item}" for item in report["interpretation"]],
        "",
        "Separate automatic corrections:",
        report["automatic_corrections"]["explanation"],
        *[f"- {item}" for item in report["automatic_corrections"]["repository_menu_evidence_only"]],
        "",
        "Practical limits:",
        *[f"- {item}" for item in report["limits"]],
        "",
        "Reproduction: run tools/jpeg_experiments/native_tone_probe_v2.py using a Python environment with Unicorn,",
        "passing --rtos with the original RTOS paths listed above, --base with the manifest below, and --out-dir with a fresh output directory.",
        f"Base manifest: {report['base_manifest']['path']}",
        f"Base manifest SHA-256: {report['base_manifest']['sha256']}",
        f"Unicorn version: {report['runtime']['unicorn']}",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rtos", type=Path, nargs="+", required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    targets = [output / "native-tone-controls.json", output / "native-tone-controls.txt"]
    if any(target.exists() for target in targets):
        parser.error("Output evidence already exists; choose a fresh output directory")
    report = probe(args.rtos, args.base)
    output.mkdir(parents=True, exist_ok=True)
    with targets[0].open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    with targets[1].open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(report_text(report))
    print(json.dumps({"outputs": [str(target) for target in targets], "measured": report["measured"], "identical_curves_across_builds": report["all_supplied_profiles_produce_identical_curves"], "automatic_corrections_tested": False}, indent=2))


if __name__ == "__main__":
    main()
