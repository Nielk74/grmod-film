"""Read-only packaging regressions against the final current artifact set.

Negative cases substitute bytes in memory or modify copied JSON dictionaries;
no delivered file, build output or source is written. Run from the new worktree:
    python tools/loaded-ui/native/check_package_diag_f.py
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'tools/loaded-ui/native/package_diag_f.py'
spec = importlib.util.spec_from_file_location('package_diag_f_under_test', SOURCE)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
OUT, BUILD = package.OUT, package.BUILD


class PackageBindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = (OUT / 'rollback/fwdc239b.bin').read_bytes()
        cls.image = (OUT / 'fwdc239b.bin').read_bytes()
        cls.report = json.loads((OUT / 'build-report.json').read_text(encoding='utf-8'))
        cls.manifest = json.loads((BUILD / 'payload-manifest.json').read_text(encoding='utf-8'))
        cls.adapter = json.loads((OUT / 'adapter-verification.json').read_text(encoding='utf-8'))
        cls.hooks = json.loads((OUT / 'hooks-verification.json').read_text(encoding='utf-8'))
        cls.inputs = (cls.pack, cls.image, cls.report, cls.manifest, cls.adapter, cls.hooks)
        # If the real set is stale, stop here: a different rejection must never
        # make a negative test appear to prove its intended guard.
        cls.baseline = package.validate_artifacts(*cls.inputs)

    def verify(self, **replace):
        names = ('pack', 'image', 'report', 'manifest', 'adapter', 'hooks')
        return package.validate_artifacts(*(replace.get(name, getattr(self, name)) for name in names))

    def reject_changed_bytes(self, target, message):
        target = target.resolve()
        original = Path.read_bytes

        def read_bytes(path):
            data = original(path)
            return data + b'\x01' if path.resolve() == target else data

        with patch.object(Path, 'read_bytes', read_bytes):
            with self.assertRaisesRegex(ValueError, message):
                self.verify()

    def test_current_actual_artifacts_are_bound(self):
        self.assertEqual(self.verify()['imageSha256'], package.sha(self.image))
        self.assertEqual(len(self.baseline['sourceHashes']), len(self.manifest['sourceHashes']))

    def test_altered_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'delivered image differs'):
            self.verify(image=self.image + b'\x01')

    def test_stale_source_hash_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['sourceHashes']['tools/loaded-ui/native/camera_diag_f.c'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source changed after linking'):
            self.verify(manifest=manifest)

    def test_changed_current_source_bytes_are_rejected(self):
        self.reject_changed_bytes(ROOT / 'tools/loaded-ui/native/camera_diag_f.c',
                                  'source changed after linking')

    def test_missing_required_source_hash_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        del manifest['sourceHashes']['tools/loaded-ui/native/camera_diag_f.c']
        with self.assertRaisesRegex(ValueError, 'manifest omits required source'):
            self.verify(manifest=manifest)

    def test_altered_actual_elf_is_rejected(self):
        self.reject_changed_bytes(BUILD / 'loaded-payload.elf', 'actual linked ELF differs')

    def test_altered_actual_payload_is_rejected(self):
        self.reject_changed_bytes(BUILD / 'loaded-payload.bin', 'actual payload differs')

    def test_altered_current_patched_rtos_is_rejected(self):
        self.reject_changed_bytes(BUILD / 'patched-rtos.bin', 'actual patched RTOS differs')

    def test_mismatched_adapter_report_is_rejected(self):
        adapter = copy.deepcopy(self.adapter)
        adapter['patched_rtos_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'actual patched RTOS differs'):
            self.verify(adapter=adapter)

    def test_mismatched_hook_report_is_rejected(self):
        hooks = copy.deepcopy(self.hooks)
        hooks['patchedRtosSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'actual patched RTOS differs'):
            self.verify(hooks=hooks)

    def test_missing_instruction_cost_evidence_is_rejected(self):
        adapter = copy.deepcopy(self.adapter)
        adapter.pop('instruction_costs')
        with self.assertRaisesRegex(ValueError, 'must include measured hook instruction_costs'):
            self.verify(adapter=adapter)


if __name__ == '__main__':
    unittest.main(verbosity=2)
