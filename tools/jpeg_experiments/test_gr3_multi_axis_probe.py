"""Real native code, two independent film blocks, and immutable source evidence."""
import importlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("gr3_multi_axis_probe.py")


class Gr3MultiAxisProbeTests(unittest.TestCase):
    def module(self):
        self.assertTrue(PROBE.is_file(), "the GR III native multi-axis probe is missing")
        return importlib.import_module("gr3_multi_axis_probe")

    def test_official_layout_is_not_the_gr4_scaled_copy_rule(self):
        probe = self.module()
        data = probe.load_profile("gr3")[0]
        result = probe.inspect_layout(data)
        self.assertEqual(result["record_words"], ["0x53dc3198", "0x53dc2bb8", "0x55019828", "0x55019848", "0x53dc2bcc", "0x53dc3a40"])
        self.assertEqual(result["factory_distinct_multi_axis_records"], 1)
        self.assertEqual(result["matrix_block_bytes"], 2160)
        self.assertEqual(result["matrix_row_sum_counts"], {"512": 3, "1024": 177})
        self.assertFalse(result["follows_gr4_scaled_copy_rule"])

    def test_native_selection_packs_all_words_and_isolates_two_films(self):
        probe = self.module()
        data = probe.load_profile("gr3")[0]
        before = bytes(data)
        result = probe.emulate_isolation(data)
        self.assertEqual(data, before)
        self.assertEqual(result["matrix_words_read_per_case"], [540, 540, 540, 540, 540])
        self.assertTrue(result["stock_before_equals_stock_after"])
        self.assertTrue(result["film_a_before_equals_film_a_after_b"])
        self.assertTrue(result["different_film_outputs"])
        self.assertEqual(result["selected_looks"], [11, 64, 65, 64, 11])
        self.assertTrue(result["original_rtos_bytes_unchanged"])
        self.assertEqual(result["hardware_verified"], False)

    def test_unknown_or_changed_rtos_is_rejected(self):
        probe = self.module()
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            probe.validate_rtos(b"not the official firmware", "gr3")


if __name__ == "__main__":
    unittest.main()
