"""Independent geometry expectations; run with python -m unittest tools.horizon_grads.test_horizon."""
import math
from pathlib import Path
import struct
import tempfile
import unittest
import json

import numpy as np
from PIL import Image

from tools.horizon_grads.metadata import decode_level, read_metadata, safe_output
from tools.horizon_grads.process import focal_pixels, horizon_distance, make_mask, apply_grad


def note(payload):
    # RICOH offsets are relative to the start of the MakerNote, not EXIF TIFF.
    return b"RICOH\0II" + struct.pack("<H", 1) + struct.pack("<HHII", 0x022b, 7, len(payload), 26) + b"\0" * 4 + payload


class MetadataTests(unittest.TestCase):
    def test_real_record_and_signed_half_degrees(self):
        # AK000056.JPG's exact 19-byte block, with no private fields.
        result = decode_level(note(bytes.fromhex("010300f9ffe6fffeffc102350032fc4000e600")))
        self.assertEqual((result["camera_orientation"], result["roll_deg"], result["pitch_deg"]), (3, 3.5, 13))
        self.assertTrue(result["valid"])

    def test_missing_truncated_bad_version_and_extreme_noop(self):
        for data in (b"", b"RICOH\0II\xff\xff", note(bytes.fromhex("0001000400040040000900f6ff40042c00d3ff")),
                     note(b"\x01\x00\0" + struct.pack("<hh", 32767, 0) + b"\0" * 12)):
            self.assertFalse(decode_level(data)["valid"])

    def test_output_cannot_alias_source(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source"
            source.mkdir()
            for out in (source, source / "nested"):
                with self.assertRaises(ValueError):
                    safe_output(out, [source])
            safe_output(Path(td) / "output", [source])


class GeometryTests(unittest.TestCase):
    def test_focal_from_stored_dimensions_is_invariant_after_exif_quarter_turn(self):
        # The caller must compute f from stored, then uniformly scale for display.
        f = focal_pixels(6000, 4000, 18.3, 28)
        display_landscape = f * max(1800, 1200) / max(6000, 4000)
        display_portrait = f * max(1200, 1800) / max(6000, 4000)
        self.assertEqual(display_portrait, display_landscape)
    def test_centered_horizon_and_correct_pitch_sign(self):
        w, h, f = 101, 101, 100
        d = horizon_distance(w, h, f, 0, 0)
        self.assertEqual(float(d[50, 50]), 0)
        self.assertGreater(d[0, 50], 0)
        self.assertLess(d[100, 50], 0)
        # Upward pitch puts the earth horizon lower, by f*tan(pitch).
        d = horizon_distance(w, h, f, 0, math.degrees(math.atan(0.2)))
        self.assertAlmostEqual(float(d[70, 50]), 0, places=4)

    def test_positive_clockwise_camera_roll_horizon_slopes_up_to_right(self):
        d = horizon_distance(101, 101, 100, 45, 0)
        self.assertAlmostEqual(float(d[25, 75]), 0, places=4)
        self.assertLess(float(d[50, 75]), 0)

    def test_geometry_scales_and_center_crop_narrows_fov(self):
        f = focal_pixels(6000, 4000, 18.3, 28)
        self.assertAlmostEqual(f, 6000 * 18.3 / 23.4, places=4)
        self.assertAlmostEqual(focal_pixels(3000, 2000, 18.3, 28), f / 2, places=4)
        self.assertAlmostEqual(focal_pixels(6000, 4000, 18.3, 35), f * 35 / 28, places=4)

    def test_mask_noop_and_no_ground_change(self):
        metadata = {"valid": True, "roll_deg": 0, "pitch_deg": 0, "focal_px": 100}
        mask = make_mask(101, 101, metadata)
        self.assertTrue(np.all(mask[50:] == 0))
        self.assertGreater(mask[0, 50], 0.99)
        self.assertTrue(np.all(make_mask(101, 101, {**metadata, "valid": False}) == 0))
        self.assertTrue(np.all(make_mask(101, 101, {**metadata, "pitch_deg": 70}) == 0))

    def test_full_strength_neutral_is_one_stop_in_linear_light(self):
        rgb = np.full((2, 2, 3), 0.8, dtype=np.float32)
        after = apply_grad(rgb, np.ones((2, 2), np.float32), "neutral", 1)
        def linear(x):
            return ((x + 0.055) / 1.055) ** 2.4
        np.testing.assert_allclose(linear(after), linear(rgb) / 2, atol=1e-6)
        np.testing.assert_array_equal(apply_grad(rgb, np.zeros((2, 2), np.float32), "tobacco", 1), rgb)
        np.testing.assert_array_equal(apply_grad(rgb, np.ones((2, 2), np.float32), "off", 1), rgb)

    def test_brightness_weight_preserves_black_without_claiming_segmentation(self):
        rgb = np.array([[[0, 0, 0], [1, 1, 1]]], dtype=np.float32)
        after = apply_grad(rgb, np.ones((1, 2), np.float32), "neutral", 1, weighted=True)
        np.testing.assert_array_equal(after[0, 0], rgb[0, 0])
        self.assertLess(float(after[0, 1, 0]), 0.8)


class ExportTests(unittest.TestCase):
    def test_film_grid_interpolation_preserves_identity_and_corners(self):
        from tools.horizon_grads.measure import trilinear
        grid = np.stack(np.meshgrid(*([np.linspace(0, 1, 3)] * 3), indexing="ij"), -1)
        rgb = np.array([[[0, 0, 0], [1, 1, 1], [0.11, 0.53, 0.78]]], dtype=np.float32)
        np.testing.assert_allclose(trilinear(rgb, grid), rgb, atol=1e-6)

    def test_two_renders_remain_verifiable(self):
        from tools.horizon_grads.run import render, verify
        from tools.horizon_grads.metadata import digest
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            out.mkdir()
            source = Path(td) / "source.jpg"
            Image.fromarray(np.full((48, 72, 3), 170, dtype=np.uint8)).save(source)
            record = {"id": "synthetic", "path": str(source), "sha256_before": digest(source),
                      "valid": True, "stored_size": [72, 48], "focal_mm": 18.3, "focal35_mm": 28,
                      "roll_deg": 0, "pitch_deg": 0}
            (out / "audit.json").write_text(json.dumps([record]), encoding="utf-8")
            selected = Path(td) / "selection.json"
            selected.write_text(json.dumps({"sources": [{"id": "synthetic", "purpose": "rerender regression"}]}), encoding="utf-8")
            for _ in range(2):
                render(out, 200, selected)
                verify(out)


@unittest.skipUnless((Path("C:/Users/Antoine/Pictures/Ricoh") / "AK000069.JPG").exists(), "local source collection absent")
class RealSourceTests(unittest.TestCase):
    def test_actual_landscape_and_portrait_decode_different_real_attitudes(self):
        root = Path("C:/Users/Antoine/Pictures/Ricoh")
        for name, angles, orientation in (("AK000069.JPG", (-0.5, -9.5), 1), ("AK000073.JPG", (0, -11), 8)):
            path = root / name
            from tools.horizon_grads.metadata import digest
            before = digest(path)
            meta = read_metadata(path)
            self.assertTrue(meta["valid"])
            self.assertEqual((meta["roll_deg"], meta["pitch_deg"]), angles)
            self.assertEqual(meta["exif_orientation"], orientation)
            f = focal_pixels(*meta["stored_size"], meta["focal_mm"], meta["focal35_mm"]) / 10
            w, h = (int(v / 10) for v in meta["display_size"])
            mask = make_mask(w, h, {**meta, "focal_px": f})
            self.assertGreater(float(mask.max()), 0.5)
            self.assertTrue(np.all(mask[-1] == 0))
            self.assertEqual(digest(path), before)

    def test_actual_stripped_edit_and_state_zero_are_conservative_noops(self):
        root = Path("C:/Users/Antoine/Pictures/Ricoh")
        for name in ("AK000065-edited.jpg", "R0000022.JPG"):
            meta = read_metadata(root / name)
            self.assertFalse(meta["valid"])
            self.assertTrue(np.all(make_mask(100, 100, meta) == 0))


if __name__ == "__main__":
    unittest.main()
