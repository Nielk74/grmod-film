"""Read-only GR III/IIIx multi-axis ABI research using real ARM instructions.

Run with research/camera-ui/venv/Scripts/python.exe. Unicorn and Capstone are
already available there. This writes JSON/text evidence only, never firmware.
It proves descriptor selection and register packing, not ISP pixel semantics.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE, RAM, RAM_SOURCE, RAM_LENGTH = 0x53000000, 0x55000000, 0x5407B540, 0x3A080
MA_TABLE, MA_RECORD, MATRIX_BLOCK = 0x55018CF0, 0x53DC2BA0, 0x53DC31D0
SELECTOR, SELECTOR_END, CONSUMER, PACKER = 0x536DC2B0, 0x536DC2BC, 0x536DF484, 0x536DF55C
BLOCK_BYTES, PACKED_BYTES = 2160, 8192
PROFILES = {
    "gr3": {
        "official": "research/camera-ui/downloads/gr3_v210/fwdc239b.bin",
        "rtos": "research/camera-ui/hardware-prep/gr3-210-rtos.bin",
        "official_sha256": "d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4",
        "rtos_sha256": "8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67",
    },
    "gr3x": {
        "official": "research/camera-ui/downloads/gr3x_v160/fwdc243b.bin",
        "rtos": "research/camera-ui/evidence/gr3x-160-rtos.bin",
        "official_sha256": "708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7",
        "rtos_sha256": "0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6",
    },
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def offset(address: int) -> int:
    if RAM <= address < RAM + RAM_LENGTH:
        address = RAM_SOURCE + address - RAM
    return address - BASE


def words(data: bytes, address: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{count}I", data, offset(address))


def validate_rtos(data: bytes, model: str) -> None:
    if sha(data) != PROFILES[model]["rtos_sha256"]:
        raise ValueError(f"{model}: RTOS SHA-256 differs from the exact official baseline")


def load_profile(model: str) -> tuple[bytes, dict]:
    profile = PROFILES[model]
    official_path, rtos_path = ROOT / profile["official"], ROOT / profile["rtos"]
    official = official_path.read_bytes()
    if sha(official) != profile["official_sha256"]:
        raise ValueError(f"{model}: official container SHA-256 differs from the verified baseline")
    data = rtos_path.read_bytes()
    validate_rtos(data, model)
    return data, {
        "model": model,
        "official_path": str(official_path), "official_sha256": sha(official),
        "rtos_path": str(rtos_path), "rtos_sha256": sha(data),
        "rtos_length": len(data),
        "source_mode": "read-only; previously extracted RTOS authenticated against core/src/fw/gr3x/profile.ts",
    }


def inspect_layout(data: bytes) -> dict:
    table = words(data, MA_TABLE, 26)
    record = words(data, MA_RECORD, 6)
    arrays = [words(data, record[k], 8) for k in (2, 3)]
    assert len(set(table)) == 1 and table[11] == MA_RECORD
    assert arrays[0] == (MATRIX_BLOCK,) * 8
    assert arrays[1] == (0x53DC2BF8,) * 8
    matrix = struct.unpack_from("<540i", data, offset(MATRIX_BLOCK))
    row_sums = Counter(sum(matrix[k:k + 3]) for k in range(0, 540, 3))
    identity = (1024, 0, 0, 0, 1024, 0, 0, 0, 1024)
    # Compare the actual bytes against the rule used by color/hue.ts on GR IV.
    # Rounding ties are immaterial to the failing first sector: 1024 != 420*15/16.
    differences = []
    for sector in range(12):
        copy0 = matrix[sector * 45:sector * 45 + 9]
        for copy in range(1, 5):
            for k in range(9):
                expected = int(copy0[k] * (16 - copy) / 16 + 0.5)
                actual = matrix[sector * 45 + copy * 9 + k]
                if abs(actual - expected) > 1:
                    differences.append({"assumed_sector": sector, "assumed_copy": copy,
                                        "coefficient": k, "actual": actual, "gr4_rule": expected})
    return {
        "table_address": hex(MA_TABLE), "table_entries": 26,
        "factory_distinct_multi_axis_records": len(set(table)),
        "record_address": hex(MA_RECORD), "record_words": [hex(v) for v in record],
        "record_bytes": 24,
        "matrix_pointer_array": [hex(v) for v in arrays[0]],
        "other_pointer_array": [hex(v) for v in arrays[1]],
        "selected_array_index": 4,
        "matrix_block_address": hex(MATRIX_BLOCK), "matrix_block_bytes": BLOCK_BYTES,
        "matrix_block_sha256": sha(data[offset(MATRIX_BLOCK):offset(MATRIX_BLOCK) + BLOCK_BYTES]),
        "matrix_count_if_grouped_as_3x3": 60,
        "first_3x3": list(matrix[:9]),
        "following_identity_matrix_count": sum(matrix[k:k + 9] == identity for k in range(9, 540, 9)),
        "matrix_row_sum_counts": {str(k): v for k, v in sorted(row_sums.items())},
        "follows_gr4_scaled_copy_rule": not differences,
        "gr4_rule_difference_count": len(differences), "gr4_rule_first_difference": differences[0],
        "word0_halfwords_16": list(struct.unpack_from("<16H", data, offset(record[0]))),
        "word1_bytes_20": list(data[offset(record[1]):offset(record[1]) + 20]),
        "word3_region_bytes": 1440,
        "word3_region_all_zero": not any(data[offset(arrays[1][0]):offset(arrays[1][0]) + 1440]),
        "word4_halfwords_22": list(struct.unpack_from("<22H", data, offset(record[4]))),
        "word5_first_9_signed_halfwords": list(struct.unpack_from("<9h", data, offset(record[5]))),
        "grouping_status": "60 3x3 matrices by byte count; 12 hue sectors x 5 copies/order is unverified on GR III",
    }


def emulate_isolation(data: bytes) -> dict:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
    from unicorn import arm_const as reg

    original_hash = sha(data)
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    cpu.mem_map(BASE, 0x1100000)
    cpu.mem_write(BASE, data)
    cpu.mem_map(RAM, 0x40000)
    cpu.mem_write(RAM, data[RAM_SOURCE - BASE:RAM_SOURCE - BASE + RAM_LENGTH])
    cpu.mem_map(0x62000000, 0x100000)
    stop = 0x63000000
    cpu.mem_map(stop, 0x1000)
    # All synthetic records and tables exist only in emulator RAM.
    table, records, arrays, blocks = 0x62000000, [0x62001000, 0x62001100], [0x62002000, 0x62002100], [0x62003000, 0x62004000]
    descriptor, obj, packed = 0x62006000, 0x62008000, 0x6200A000

    def put(address: int, *values: int) -> None:
        cpu.mem_write(address, struct.pack(f"<{len(values)}I", *values))

    def read_words(address: int, count: int) -> tuple[int, ...]:
        return struct.unpack(f"<{count}I", cpu.mem_read(address, count * 4))

    assert words(data, SELECTOR, 1)[0] == 0xE79CC101  # ldr ip,[ip,r1,lsl #2]
    assert words(data, SELECTOR + 8, 1)[0] == 0xE584C00C  # str ip,[r4,#0xc]
    assert words(data, 0x536DF49C, 1)[0] == 0xE591500C  # descriptor+0xc
    assert words(data, 0x536DF4D0, 1)[0] == 0xE5933010  # pointer-array index 4
    assert words(data, 0x536DF508, 1)[0] == 0xE3A02E87  # mov r2,#0x870

    stock_record = bytes(cpu.mem_read(MA_RECORD, 24))
    stock_block = bytes(cpu.mem_read(MATRIX_BLOCK, BLOCK_BYTES))
    # Two neutral-preserving coefficient sets, with negative entries to exercise
    # signed-to-12-bit register packing. Their artistic meaning is not assumed.
    markers = [(1, (980, 31, 13, -17, 1020, 21, 43, -8, 989)),
               (58, (1001, 18, 5, 12, 1030, -18, -11, 5, 1030))]
    for record, array, block, (matrix_index, values) in zip(records, arrays, blocks, markers):
        cpu.mem_write(record, stock_record)
        put(record + 8, array)
        put(array, *([block] * 8))
        cpu.mem_write(block, stock_block)
        cpu.mem_write(block + matrix_index * 36, struct.pack("<9i", *values))
    extended = list(words(data, MA_TABLE, 26)) + [MA_RECORD] * (84 - 26)
    extended[64], extended[65] = records
    put(table, *extended)

    def call(address: int, r0: int, r1: int) -> None:
        cpu.reg_write(reg.UC_ARM_REG_SP, 0x620F0000)
        cpu.reg_write(reg.UC_ARM_REG_LR, stop)
        cpu.reg_write(reg.UC_ARM_REG_R0, r0)
        cpu.reg_write(reg.UC_ARM_REG_R1, r1)
        cpu.emu_start(address, stop, count=200000)
        assert cpu.reg_read(reg.UC_ARM_REG_PC) == stop, "native call did not return"

    traces = []
    outputs = []
    counts = []
    for look in [11, 64, 65, 64, 11]:
        cpu.mem_write(descriptor, bytes(0x200))
        cpu.mem_write(obj, bytes(0x900))
        cpu.mem_write(packed, bytes(PACKED_BYTES))
        cpu.reg_write(reg.UC_ARM_REG_R12, table)
        cpu.reg_write(reg.UC_ARM_REG_R1, look)
        cpu.reg_write(reg.UC_ARM_REG_R4, descriptor)
        cpu.reg_write(reg.UC_ARM_REG_R11, 0x62007000)
        cpu.emu_start(SELECTOR, SELECTOR_END, count=3)
        assert cpu.reg_read(reg.UC_ARM_REG_PC) == SELECTOR_END
        assert read_words(descriptor + 12, 1)[0] == extended[look]
        call(CONSUMER, obj, descriptor)
        selected = read_words(obj, 6)
        expected_block = blocks[look - 64] if look in (64, 65) else MATRIX_BLOCK
        assert selected[2] == expected_block
        read_offsets = set()
        register_offsets = {}
        pending_coefficient = [None]
        word4_reads = set()
        executed = []

        def on_read(_cpu, _access, address, size, _value, _context):
            if 0x53DC2BCC <= address < 0x53DC2BF8:
                word4_reads.add((address - 0x53DC2BCC, size, _cpu.reg_read(reg.UC_ARM_REG_PC)))
            if expected_block <= address < expected_block + BLOCK_BYTES:
                assert size == 4 and (address - expected_block) % 4 == 0
                read_offsets.add(address - expected_block)
                pending_coefficient[0] = address - expected_block

        def on_write(_cpu, _access, address, size, _value, _context):
            if packed <= address < packed + PACKED_BYTES and pending_coefficient[0] is not None:
                assert size == 2
                register_offsets[pending_coefficient[0]] = address - packed
                pending_coefficient[0] = None

        def on_code(_cpu, address, _size, _context):
            executed.append(address)

        hook = cpu.hook_add(UC_HOOK_MEM_READ, on_read)
        write_hook = cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
        code_hook = cpu.hook_add(UC_HOOK_CODE, on_code)
        call(PACKER, obj, packed)
        cpu.hook_del(hook)
        cpu.hook_del(write_hook)
        cpu.hook_del(code_hook)
        assert read_offsets == set(range(0, BLOCK_BYTES, 4)), "not every coefficient was read"
        assert set(register_offsets) == read_offsets, "a coefficient has no corresponding register write"
        counts.append(len(read_offsets))
        output = bytes(cpu.mem_read(packed, PACKED_BYTES))
        source_values = struct.unpack("<540i", cpu.mem_read(expected_block, BLOCK_BYTES))
        for k, expected in enumerate(source_values):
            actual = struct.unpack_from("<H", output, register_offsets[k * 4])[0] & 0xFFF
            assert actual == expected & 0xFFF, (look, k, actual, expected)
        outputs.append(output)
        if look in (64, 65):
            matrix_index, values = markers[look - 64]
            # Follow actual source reads and register writes: register-bank gaps
            # make an assumed global matrix stride incorrect at later indices.
            actual = tuple(struct.unpack_from("<H", output, register_offsets[(matrix_index * 9 + k) * 4])[0] & 0xFFF
                           for k in range(9))
            assert actual == tuple(v & 0xFFF for v in values), (look, actual)
        traces.append({"look": look, "selected_record": hex(extended[look]),
                       "consumer_words": [hex(v) for v in selected], "packed_sha256": sha(output),
                       "packer_instruction_count": len(executed), "packer_last_instruction": hex(max(executed)),
                       "coefficient_register_offsets_first18": [hex(register_offsets[k * 4]) for k in range(18)],
                       "coefficient_register_offsets_last9": [hex(register_offsets[k * 4]) for k in range(531, 540)],
                       "word4_control_reads": [{"offset": hex(at), "bytes": size, "instruction": hex(pc)} for at, size, pc in sorted(word4_reads)]})
    assert outputs[0] == outputs[4] and outputs[1] == outputs[3]
    assert outputs[1] != outputs[2] and outputs[0] != outputs[1]
    assert bytes(cpu.mem_read(BASE, len(data))) == data, "emulator modified original RTOS memory"
    assert bytes(cpu.mem_read(RAM + MA_TABLE - RAM, 26 * 4)) == struct.pack("<26I", *words(data, MA_TABLE, 26))
    return {
        "proof": "actual ARM instructions executed by Unicorn; synthetic extended table and two film records in emulator RAM",
        "selected_looks": [11, 64, 65, 64, 11], "matrix_words_read_per_case": counts,
        "stock_before_equals_stock_after": outputs[0] == outputs[4],
        "film_a_before_equals_film_a_after_b": outputs[1] == outputs[3],
        "different_film_outputs": outputs[1] != outputs[2],
        "original_rtos_bytes_unchanged": sha(data) == original_hash,
        "original_emulated_rtos_and_factory_table_unchanged": True,
        "traces": traces,
        "changed_register_byte_counts_vs_stock": [sum(a != b for a, b in zip(outputs[0], out)) for out in outputs[1:3]],
        "native_addresses": {"selector": hex(SELECTOR), "consumer": hex(CONSUMER), "register_packer": hex(PACKER),
                             "descriptor_pointer_read": "0x536df49c", "matrix_array_index4": "0x536df4d0",
                             "alternate_path_copy_length_2160": "0x536df508"},
        "hardware_verified": False,
        "limitations": [
            "The full descriptor-builder and camera pipeline do not run: the exact native table-load instructions are exercised with a synthetic extended table.",
            "The descriptor+0x94 normal path is exercised; its nonzero override path is identified in disassembly only.",
            "The register packer copies coefficient/control data. It does not render pixels or establish sector geometry, matrix order, copy scaling, or stage order.",
            "No firmware file, card, camera, product source, or existing image is modified.",
        ],
    }


def native_disassembly(data: bytes) -> list[str]:
    import capstone
    dis = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    lines = []
    for address, size in [(SELECTOR, 12), (0x536DF498, 0x84), (PACKER, 0x34),
                          (0x536E42B0, 0x88), (0x536E4400, 0x70)]:
        for ins in dis.disasm(data[offset(address):offset(address) + size], address):
            lines.append(f"{ins.address:08x} {ins.mnemonic} {ins.op_str}")
    return lines


FUTURE_MANIFEST = (
    "After ISP semantics are characterized: core/src/fw/gr3x/multi-axis.ts (new, GR III-specific verified block/control layout); "
    "core/src/fw/gr3x/films-r10.ts (own multi-axis record/table entry per film); core/src/fw/gr3x/image-control.ts (hue input validation, block allocation, fingerprint); "
    "core/src/fw/gr3x/look-recipe.ts (optional hueQ10 serialization/readback, preserve legacy recipes); core/src/color/gr3x-import.ts (guarded hue fit and final quantized validation); "
    "core/src/color/hue-fit.ts (camera-model injection, retaining GR IV default); core/src/color/camera.ts (evaluate the complete serialized quantized format); "
    "core/src/app/engine.ts (read GR III Standard stage, pass hue fitting option and build input); "
    "ui/src/store.ts (request hue fitting and preserve result in film requests); new core/test/gr3x-hue.test.ts plus existing GR III/IIIx equivalence, "
    "film recipe and GR IV unchanged tests. Shared core/src/color/hue.ts must retain the current GR IV writer unless a model-specific codec is added. "
    "A GR III fitter must compare fully quantized Q13 matrix, all 256 curve samples, Q9 post matrix and the verified hue stage against the quantized plain fit, "
    "using held-out colors and protected greys/near-neutrals/skin. Native hue absence limits selective fitting fidelity; existing matrices/curves already express creative film looks."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="02-native-hue-research destination; JSON/text only")
    args = parser.parse_args()
    results = []
    for model in PROFILES:
        data, source = load_profile(model)
        results.append({"source": source, "layout": inspect_layout(data), "native_execution": emulate_isolation(data),
                        "disassembly": native_disassembly(data)})
    assert results[0]["layout"] == results[1]["layout"], "GR III/IIIx multi-axis layouts differ"
    report = {
        "status": "native pointer selection and register packing verified; ISP hue interpretation unverified",
        "interpreter": sys.executable,
        "profiles": results,
        "conclusion": "Own film descriptors/blocks are representable and consumed independently. The GR IV hueBlockBytes writer is incompatible with the GR III factory normalization/copy data.",
        "word4_threshold_conclusion": "The observed 22 halfwords are packed as control fields. The examined CPU consumer/packer contains no per-pixel sector selector and does not establish 12 x 5 grouping. ISP hardware characterization is required before assigning per-hue meaning or fitting a native hue block.",
        "future_product_file_manifest": FUTURE_MANIFEST,
        "no_product_or_firmware_changes": True,
    }
    output = args.output.resolve()
    source_dirs = [ROOT / "core", ROOT / "ui", ROOT / "research/camera-ui/downloads", ROOT / "research/camera-ui/evidence", ROOT / "research/camera-ui/hardware-prep"]
    if any(output == p.resolve() or p.resolve() in output.parents for p in source_dirs):
        raise ValueError("report output overlaps a protected source directory")
    output.mkdir(parents=True, exist_ok=True)
    (output / "layout.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    text = "\n\n".join([
        "GR III / IIIx native multi-axis research\n" + report["status"],
        report["conclusion"],
        "Actual data: shared six-word record 0x53dc2ba0; matrix array 0x55019828, entry 4 -> 0x53dc31d0 (2160 bytes). First 3x3 rows sum to 512, the following 59 identity matrices sum to 1024. This differs from the GR IV scaled-copy rule. The block's 60 matrices do not prove 12 hue sectors x 5 copies.",
        "Actual native execution: selector 0x536dc2b0, consumer 0x536df484, packer 0x536df55c. Cases 11, 64, 65, 64, 11 read all 540 coefficients each. Film A and B have independent descriptors and blocks. Repeated stock and film A results are byte-identical. Original RTOS memory and factory table stay unchanged.",
        report["word4_threshold_conclusion"],
        "No pixel rendering, ISP execution, camera appearance, or hardware safety is established. No production hue port or candidate firmware was produced. The separate film LUT/matrix/curve path can already make creative film appearances; the missing selective stage affects fitting accuracy, not the existence of film looks.",
        "Future product integration manifest (conditional on verified ISP semantics):\n" + FUTURE_MANIFEST,
        "Interpreter: " + sys.executable,
        "Exact native instruction excerpts:\n" + "\n".join(results[0]["disassembly"]),
    ])
    (output / "report.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(output), "profiles": len(results), "status": report["status"]}))


if __name__ == "__main__":
    main()
