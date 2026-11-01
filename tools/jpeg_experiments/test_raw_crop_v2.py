"""DNG field-of-view and already-oriented LibRaw crop checks."""

from pathlib import Path
import importlib.util

import numpy as np
import pytest


@pytest.fixture(scope="module")
def ops():
    path = Path(__file__).with_name("raw_crop_v2.py")
    spec = importlib.util.spec_from_file_location("jpeg_raw_crop_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _orient(image, flip):
    if flip & 1:
        image = image[:, ::-1]
    if flip & 2:
        image = image[::-1]
    if flip & 4:
        image = image.transpose(1, 0, 2)
    return image


@pytest.mark.parametrize("flip", range(8))
def test_all_libraw_orientation_flags_crop_the_same_sensor_region(ops, flip):
    raw = np.arange(7 * 9 * 3, dtype=np.float32).reshape(7, 9, 3)
    scene = _orient(raw, flip)
    saved = scene.copy()
    metadata = {"active_dimensions": [9, 7], "default_crop_active_xywh": [2, 1, 5, 3],
                "libraw_flip": flip}
    result, record = ops.apply_camera_crop(scene, metadata)
    expected = _orient(raw[1:4, 2:7], flip)
    np.testing.assert_array_equal(result, expected)
    np.testing.assert_array_equal(scene, saved)
    assert record["decode_scale"] == 1
    assert record["cropped_dimensions"] == [expected.shape[1], expected.shape[0]]


@pytest.mark.parametrize("flip", [0, 3, 5, 6])
def test_half_size_decode_uses_half_resolution_crop_coordinates(ops, flip):
    raw = np.arange(8 * 12 * 3, dtype=np.float32).reshape(8, 12, 3)
    scene = _orient(raw, flip)
    metadata = {"active_dimensions": [24, 16], "default_crop_active_xywh": [4, 2, 12, 10],
                "libraw_flip": flip}
    result, record = ops.apply_camera_crop(scene, metadata)
    np.testing.assert_array_equal(result, _orient(raw[1:6, 2:8], flip))
    assert record["decode_scale"] == .5


def test_incorrect_or_pre_resized_decode_is_rejected(ops):
    metadata = {"active_dimensions": [24, 16], "default_crop_active_xywh": [4, 2, 12, 10],
                "libraw_flip": 0}
    with pytest.raises(ValueError, match="full or half"):
        ops.apply_camera_crop(np.zeros((10, 12, 3)), metadata)


@pytest.mark.parametrize("rect", [[-1, 0, 4, 4], [0, 0, 30, 4], [0, 0, 0, 4], [1.5, 0, 4, 4]])
def test_invalid_or_fractional_crop_is_rejected(ops, rect):
    metadata = {"active_dimensions": [24, 16], "default_crop_active_xywh": rect,
                "libraw_flip": 0}
    with pytest.raises(ValueError):
        ops.apply_camera_crop(np.zeros((16, 24, 3)), metadata)


@pytest.mark.parametrize("area,name,origin,size,flip,oriented_rect", [
    ("Ricoh2", "AK000011", [1330, 892], [3360, 2240], 0, [1330, 892, 4690, 3132]),
    ("Ricoh2", "AK000025", [10, 12], [6000, 4000], 0, [10, 12, 6010, 4012]),
    ("Ricoh", "R0000001", [10, 12], [6000, 4000], 6, [12, 10, 4012, 6010]),
])
def test_actual_ricoh_default_crops_and_orientation_metadata(ops, area, name, origin, size, flip, oriented_rect):
    path = Path("C:/Users/Antoine/Pictures") / area / (name + ".DNG")
    if not path.is_file():
        pytest.skip("Local read-only Ricoh fixture is unavailable")
    metadata = ops.camera_crop_metadata(path)
    assert metadata["active_dimensions"] == [6020, 4024]
    assert metadata["default_crop_active_xywh"] == origin + size
    assert metadata["libraw_flip"] == flip
    assert metadata["default_crop_raw_xywh"] == [origin[0] + 58, origin[1] + 28] + size
    dimensions = [6020, 4024] if not flip & 4 else [4024, 6020]
    scene = np.broadcast_to(np.zeros((1, 1, 3), dtype=np.float32), (dimensions[1], dimensions[0], 3))
    cropped, record = ops.crop_raw_to_camera_frame(scene, path)
    assert record["applied_crop_xyxy"] == oriented_rect
    expected = size if not flip & 4 else size[::-1]
    assert [cropped.shape[1], cropped.shape[0]] == expected
    assert record["tiff_default_crop_matches_libraw"] is True
