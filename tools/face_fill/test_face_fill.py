"""Numerical safety and coordinate tests; private images are tested by run.py."""
import numpy as np
import pytest
import struct
from pathlib import Path

from audit import maker_entries, output_safe

from face_fill import (fill_light, skin_keeper, face_mask, srgb_to_linear,
                       map_face, merge_detections, skin_probability, blind_keeper)


def test_no_faces_exact_identity_and_overlap_does_not_stack():
    source = np.full((80, 100, 3), [.42, .29, .23], np.float32)
    empty = face_mask(source, [])
    assert np.array_equal(fill_light(source, empty), source)
    face = {"box": [20, 10, 60, 60]}
    one = face_mask(source, [face])
    assert np.array_equal(one, face_mask(source, [face, face]))
    assert one[40, 50] > .9
    assert one[0, 0] == 0


def test_lift_is_measured_in_display_linear_light_and_preserves_chroma_ratio():
    source = np.full((2, 2, 3), [.3, .2, .15], np.float32)
    mask = np.ones((2, 2), np.float32)
    result = fill_light(source, mask, ev=.75)
    before = srgb_to_linear(source)
    after = srgb_to_linear(result)
    assert np.allclose(after / before, 2 ** .75, atol=2e-5)
    assert np.allclose(after[..., 0] / after[..., 1], before[..., 0] / before[..., 1])


def test_highlights_stay_finite_no_new_clipping_and_source_not_mutated():
    source = np.array([[[1, 1, 1], [.99, .8, .5], [0, 0, 0], [.4, .25, .2]]], np.float32)
    copy = source.copy()
    out = fill_light(source, np.ones((1, 4), np.float32), ev=1)
    assert np.isfinite(out).all() and out.min() >= 0 and out.max() <= 1
    assert np.array_equal(out[0, 0], source[0, 0])
    assert out[0, 1].max() < 1
    assert np.array_equal(source, copy)


def test_skin_gate_is_exposure_tolerant_and_rejects_neutral_and_blue():
    samples = np.array([[[.64,.44,.32], [.22,.13,.09], [.42,.30,.24],
                         [.7,.7,.7], [.1,.2,.8]]], np.float32)
    p = skin_probability(samples)[0]
    assert np.all(p[:3] > .7)
    assert np.all(p[3:] < .05)


def test_keeper_keeps_film_luminance_and_unchanged_background():
    original = np.full((2, 2, 3), [.5, .32, .24], np.float32)
    film = np.full((2, 2, 3), [.6, .27, .13], np.float32)
    mask = np.array([[1, 0], [1, 0]], np.float32)
    result = skin_keeper(original, film, mask)
    weights = np.array([.2126,.7152,.0722])
    assert np.allclose(srgb_to_linear(result) @ weights, srgb_to_linear(film) @ weights, atol=2e-6)
    assert np.array_equal(result[:,1], film[:,1])
    assert np.linalg.norm(result[0,0] - original[0,0]) < np.linalg.norm(film[0,0] - original[0,0])


def test_detector_mapping_uses_independent_xy_scales_and_consensus():
    face = [10,20,30,40, 15,25, 35,25, 25,35, 18,48, 32,48, .9]
    mapped = map_face(face, (200,300), (800,1500), 320)
    assert mapped['box'] == [40,100,120,200]
    assert mapped['landmarks'][0] == [60,125]
    second = dict(mapped, scale=640, score=.85)
    accepted, rejected = merge_detections([mapped,second])
    assert len(accepted) == 1 and len(rejected) == 0
    assert accepted[0]['support_scales'] == [320,640]
    accepted, rejected = merge_detections([mapped])
    assert not accepted and len(rejected) == 1


def test_invalid_data_and_ev_are_rejected():
    rgb = np.zeros((2,2,3), np.float32)
    for ev in (-1, float('nan'), 3):
        with pytest.raises(ValueError): fill_light(rgb, np.zeros((2,2)), ev=ev)
    with pytest.raises(ValueError): face_mask(rgb, [{'box':[0,0,-1,4]}])


def test_blind_keeper_preserves_luminance_and_cannot_change_chroma_direction():
    film=np.full((2,2,3),[.65,.30,.16],np.float32)
    m=np.array([[1,0],[1,0]],np.float32)
    out=blind_keeper(film,m)
    a,b=srgb_to_linear(film),srgb_to_linear(out)
    y=a@np.array([.2126,.7152,.0722])
    assert np.allclose(b@np.array([.2126,.7152,.0722]),y,atol=1e-6)
    assert np.allclose(b[0,0]-y[0,0],.7*(a[0,0]-y[0,0]),atol=1e-6)
    assert np.array_equal(out[:,1],film[:,1])


def test_makernote_parser_reads_inline_and_offset_data_and_refuses_bad_bounds():
    header=b'RICOH\0II'+struct.pack('<H',2)
    inline=struct.pack('<HHII',0x4f,3,1,256)
    offset=struct.pack('<HHII',0x40b,7,8,38)
    fixture=header+inline+offset+b'\0'*4+struct.pack('<II',6000,4000)
    entries=maker_entries(fixture)
    assert int.from_bytes(entries[0x4f]['data'],'little')==256
    assert struct.unpack('<II',entries[0x40b]['data'])==(6000,4000)
    assert maker_entries(b'not a Ricoh MakerNote') is None
    with pytest.raises(ValueError):maker_entries(fixture[:-1])
    with pytest.raises(ValueError):maker_entries(b'RICOH\0II\x64\0')


def test_output_directory_guard_blocks_source_and_nested_sources():
    for path in ('C:/Users/Antoine/Pictures/Ricoh','C:/Users/Antoine/Pictures/Ricoh2/output/test.jpg'):
        with pytest.raises(ValueError):output_safe(path)
    assert output_safe('scratch/face-fill').name=='face-fill'


def test_many_faces_and_hot_highlights_do_not_stack_or_bleed_outside_ovals():
    rgb=np.full((100,180,3),[.56,.34,.25],np.float32)
    rgb[35:45,40:50]=1
    faces=[{'box':[10,10,70,80]},{'box':[95,10,70,80]}]
    mask=face_mask(rgb,faces)
    out=fill_light(rgb,mask)
    assert mask[50,90]==0
    assert np.array_equal(out[35:45,40:50],rgb[35:45,40:50])
    assert np.array_equal(out[:,85:90],rgb[:,85:90])
    assert out[50,40,0]>rgb[50,40,0] and out[50,130,0]>rgb[50,130,0]


def test_verifier_imports_the_face_fill_runner_not_the_older_jpeg_runner():
    import verify_outputs
    assert Path(verify_outputs.open_rgb.__code__.co_filename).resolve()==Path(__file__).with_name('run.py').resolve()


def test_export_verification_allows_icc_creation_time_but_rejects_other_tag_changes():
    from verify_outputs import profile_colour_data, SRGB
    original=SRGB.tobytes();later=bytearray(original)
    later[35]=(later[35]+1)%60
    assert profile_colour_data(original)==profile_colour_data(bytes(later))
    later[-1]^=1
    assert profile_colour_data(original)!=profile_colour_data(bytes(later))
