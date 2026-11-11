"""Numerical contracts, run with python -m unittest discover -s tools/trichrome."""
import unittest
import numpy as np
import pipeline as p


class TrichromeContracts(unittest.TestCase):
    def test_static_image_is_exact_and_blue_is_frame_three(self):
        rng = np.random.default_rng(14)
        a = rng.integers(10, 245, (128, 192, 3), dtype=np.uint8)
        out, literal, report = p.reconstruct(a, [p.reduce_plane(a[..., c], 4) for c in (0, 1)],
                                             [(0., 0.), (0., 0.)], [(1., 0.), (1., 0.)])
        np.testing.assert_array_equal(out, a)
        self.assertGreater(np.abs(literal.astype(float) - a).mean(), 20)
        np.testing.assert_array_equal(out[..., 2], a[..., 2])

    def test_independent_channels_keep_temporal_ghosts(self):
        a = np.full((128, 192, 3), 50, np.uint8)
        f = [a.copy() for _ in range(3)]
        for k in range(3):
            f[k][40:80, 20 + 50*k:40 + 50*k] = 200
        out, _, _ = p.reconstruct(f[2], [p.reduce_plane(f[k][..., k], 4) for k in range(2)],
                                   [(0., 0.)]*2, [(1., 0.)]*2)
        self.assertGreater(int(out[60, 30, 0]), 195)
        self.assertLess(int(out[60, 30, 1]), 55)
        self.assertGreater(int(out[60, 80, 1]), 195)
        self.assertGreater(int(out[60, 130, 2]), 195)

    def test_translation_recovers_fractional_offset_and_rejects_flat(self):
        rng = np.random.default_rng(8)
        raw = rng.uniform(20, 230, (256, 320)).astype(np.float32)
        from PIL import Image, ImageFilter
        base = np.array(Image.fromarray(raw.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1))).astype(np.float32)
        shifted = p.warp_plane(base, -2.5, 1.25)[0]
        got = p.estimate_shift(shifted, base)
        self.assertTrue(got['accepted'], got)
        np.testing.assert_allclose(got['shift'], (2.5, -1.25), atol=.3)
        self.assertFalse(p.estimate_shift(np.ones((128,128))*100, np.ones((128,128))*100)['accepted'])

    def test_parallax_and_unrelated_images_are_rejected(self):
        rng = np.random.default_rng(11)
        a = rng.uniform(10, 240, (256, 384)).astype(np.float32)
        b = p.warp_plane(a, -5, 0)[0]
        b[:, :192] = p.warp_plane(a, 5, 0)[0][:, :192]
        self.assertFalse(p.estimate_shift(b, a)['accepted'])
        self.assertFalse(p.estimate_shift(rng.uniform(10,240,a.shape), a)['accepted'])

    def test_radiometric_fit_removes_gain_and_offset(self):
        r = np.linspace(30, 190, 10000).reshape(100, 100).astype(np.float32)
        s = r*1.1 + 4
        fit = p.fit_radiometry(s, r, np.ones_like(r,dtype=bool))
        np.testing.assert_allclose(fit['affine'], (1/1.1, -4/1.1), atol=.01)
        self.assertTrue(fit['accepted'])

    def test_crop_excludes_invalid_edges_without_wrapping(self):
        a = np.full((128,192,3),100,np.uint8)
        out, _, report = p.reconstruct(a, [p.reduce_plane(a[..., k],4) for k in range(2)],
                                        [(1.5,-.5),(-.75,1.25)], [(1,0)]*2)
        self.assertEqual(out.shape, (113,175,3))
        self.assertEqual(report['crop_xyxy'], [7,6,182,119])
        self.assertTrue(np.all(out==100))

    def test_capture_order_budget_and_cancel_reset(self):
        frame = np.full((128,192,3),100,np.uint8)
        b=p.BurstBuffer(memory_limit=4000)
        self.assertIsNone(b.submit(frame,1,'x','fixed',0))
        self.assertEqual(b.retained_bytes,1536)
        self.assertIsNone(b.submit(frame,2,'x','fixed',1))
        self.assertEqual(b.retained_bytes,3072)
        b.cancel();self.assertEqual(b.retained_bytes,0)
        with self.assertRaises(ValueError): b.submit(frame,2,'x','fixed',2)
        b.submit(frame,1,'x','fixed',3)
        with self.assertRaises(ValueError): b.submit(frame,2,'x','changed',4)
        self.assertEqual(b.retained_bytes,0)
        b.submit(frame,1,'x','fixed',0);b.submit(frame,2,'x','fixed',1)
        self.assertTrue(b.expire(20))
        self.assertEqual(b.retained_bytes,0)
        tiny=p.BurstBuffer(memory_limit=100)
        with self.assertRaises(MemoryError): tiny.submit(frame,1,'x','fixed',0)
        self.assertEqual(tiny.retained_bytes,0)

    def test_mismatch_timeout_failure_and_completion_always_clear(self):
        a=np.full((128,192,3),100,np.uint8)
        b=p.BurstBuffer()
        b.submit(a,1,'x','fixed',0)
        with self.assertRaises(ValueError): b.submit(a,2,'other','fixed',1)
        b.submit(a,1,'x','fixed',0)
        with self.assertRaises(ValueError): b.submit(a,2,'x','fixed',20)
        b.submit(a,1,'x','fixed',0)
        with self.assertRaises(ValueError): b.submit(a[:100],2,'x','fixed',1)
        b.submit(a,1,'x','fixed',0);b.submit(a,2,'x','fixed',1)
        result=b.submit(a,3,'x','fixed',2)
        self.assertFalse(result['accepted'])
        self.assertEqual(b.retained_bytes,0)

    def test_large_radiometric_drift_is_rejected(self):
        r=np.linspace(30,110,10000).reshape(100,100).astype(np.float32)
        fit=p.fit_radiometry(r*2,r,np.ones_like(r,dtype=bool))
        self.assertFalse(fit['accepted'])

    def test_end_to_end_static_and_small_moving_foreground(self):
        # Catches a guard that rejects every scene, or detail lost in capture state.
        rng=np.random.default_rng(80)
        a=rng.integers(20,200,(512,768,3),dtype=np.uint8)
        b=p.BurstBuffer()
        b.submit(a,1,'static','fixed',0);b.submit(a,2,'static','fixed',1)
        result=b.submit(a,3,'static','fixed',2)
        self.assertTrue(result['accepted'],result)
        np.testing.assert_array_equal(result['output'],a)
        frames=[a.copy() for _ in range(3)]
        for k,x in enumerate((200,280,360)):frames[k][360:400,x:x+32]=240
        b.submit(frames[0],1,'motion','fixed',0);b.submit(frames[1],2,'motion','fixed',1)
        moving=b.submit(frames[2],3,'motion','fixed',2)
        self.assertTrue(moving['accepted'],moving)
        self.assertGreater(int(moving['output'][380,216,0]),225)
        self.assertGreater(int(moving['output'][380,296,1]),225)
        np.testing.assert_array_equal(moving['output'][...,2],frames[2][...,2])
        self.assertEqual(b.retained_bytes,0)


if __name__ == '__main__':
    unittest.main()
