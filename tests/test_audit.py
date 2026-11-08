import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from image_denoising_claim_audit import phrases
from image_denoising_claim_audit.audit import claims, evidence, main, scan

POSITIVE = ('image denoising', 'image-denoising', 'imagedenoising', 'image denoising model', 'image denoising models', 'image denoising system', 'image denoising systems', 'image denoising feature', 'image denoising capability', 'image denoising support', 'supports image denoising', 'image denoising tool', 'image denoising api', 'image denoising pipeline', 'image denoising algorithm', 'image denoising library', 'image denoising framework', 'image denoising service', 'image denoising function', 'image denoising engine', 'image denoising engines', 'image denoiser', 'image denoisers', 'denoises images', 'denoise images', 'denoises photos', 'denoise photos', 'denoises pictures', 'denoise pictures', 'photo denoising', 'photo-denoising', 'photo denoiser', 'photo denoisers', 'denoises photo', 'denoise photo', 'image noise removal', 'image noise remover', 'image denoising task', 'image denoising benchmark', 'automatic image denoising', 'automated image denoising', 'denoises image files', 'denoise image files', 'image denoising software', 'image denoising app', 'image denoising program', 'denoises your photos', 'denoise my photos', 'picture denoising', 'removes image noise')
NEGATIVE = ('does not support image denoising', 'do not support image denoising', "doesn't support image denoising", "don't support image denoising", 'no image denoising', 'without image denoising', 'never performs image denoising', 'does not perform image denoising', 'image denoising not supported', 'image denoising unsupported', 'no image denoising support', 'lacks image denoising', 'missing image denoising', 'image denoising disabled', 'no image denoising capability', 'without image denoising support', 'does not provide image denoising', 'no image denoising model', 'image denoising not available', 'does not use image denoising', 'no image denoiser', 'without image denoiser', 'does not support image denoiser', 'no photo denoiser')
DIRECT = ('fastNlMeansDenoising', 'fastNlMeansDenoisingColored', 'fastNlMeansDenoisingMulti', 'denoise_nl_means', 'denoise_bilateral', 'denoise_tv_chambolle', 'denoise_tv_bregman', 'denoise_wavelet', 'wiener', 'bm3d')
GENERIC = ('denoise_image', 'image_denoising', 'denoise_photo', 'image_denoiser', 'predict_denoised_image', 'denoise_picture', 'remove_image_noise', 'image_noise_removal', 'denoise_image_file', 'predict_noise_free_image', 'denoise_grayscale', 'denoise_color_image', 'image_denoise', 'photo_denoising', 'photo_denoiser', 'denoise_your_photo', 'remove_noise_from_image', 'image_noise_reduction', 'denoise_noisy_image', 'noisy_image_denoising', 'predict_clean_image', 'denoise_frame', 'frame_denoising', 'image_denoising_model')


class AuditTests(unittest.TestCase):
    def fixture(self, files):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        return root

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = main(list(map(str, args)))
        return status, out.getvalue(), err.getvalue()

    def test_phrase_oracle(self):
        self.assertEqual(phrases.IMAGEDENOISING, POSITIVE)
        self.assertEqual(phrases.NOIMAGEDENOISING, NEGATIVE)
        self.assertEqual((len(POSITIVE), len(NEGATIVE)), (50, 24))

    def test_generic_oracle(self):
        self.assertEqual(phrases.GENERIC_NAMES, GENERIC)

    def test_direct_oracle(self):
        self.assertEqual(phrases.DIRECT_NAMES, DIRECT)

    def test_all_phrases(self):
        for phrase in POSITIVE:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), ([phrase], []))
        for phrase in NEGATIVE:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), ([], [phrase]))

    def test_span_removal(self):
        self.assertEqual(claims('does not support image denoising'), ([], [NEGATIVE[0]]))

    def test_longest_singular(self):
        self.assertEqual(claims('image denoising model'), (['image denoising model'], []))

    def test_longest_plural(self):
        self.assertEqual(claims('image denoising models'), (['image denoising models'], []))

    def test_collision(self):
        self.assertEqual(claims('denoise image files by date')[0], ['denoise image files'])

    def test_fences(self):
        self.assertEqual(claims('```text\nimage denoising\n```\n~~~\nno image denoiser\n~~~'), ([], []))

    def test_inline(self):
        self.assertEqual(claims('`image denoising`')[0], [POSITIVE[0]])

    def test_exact_matching(self):
        self.assertEqual(claims('image--denoising; denoising pictures'), ([], []))

    def test_shadowing(self):
        for name in DIRECT + GENERIC:
            for definition in ('def {0}(*args): pass', 'class {0}: pass'):
                for call in ('from lib import {0}\n{0}(data)', 'obj.{0}(data)', 'from lib import {0} as f\nf(data)'):
                    with self.subTest(name=name, definition=definition, call=call):
                        self.assertFalse(evidence(call.format(name) + '\n' + definition.format(name)))

    def test_alias_shadowing(self):
        self.assertFalse(evidence('from lib import denoise_image as f\ndef f(x): pass\nf(data)'))
        self.assertFalse(evidence('import cv2 as c\nclass c: pass\nc.fastNlMeansDenoising(data)'))

    def test_split_module(self):
        root = self.fixture({'README.md': POSITIVE[0], 'a.py': 'from lib import denoise_image as f', 'b.py': 'f(data)'})
        self.assertEqual(scan(root)[0]['severity'], 'HIGH')

    def test_complete_single_module(self):
        root = self.fixture({'README.md': POSITIVE[0], 'a.py': 'pass', 'b.py': 'x.denoise_image(data)'})
        self.assertEqual(scan(root), [])

    def test_good(self):
        root = self.fixture({'README.md': POSITIVE[0], 'app.py': 'x.denoise_image(data)'})
        self.assertEqual(self.cli('audit', root)[:2], (0, 'PASS\n'))

    def test_bad_case_json(self):
        root = self.fixture({'README.md': 'IMAGE DENOISING'})
        status, out, _ = self.cli('audit', root, '--json')
        self.assertEqual(status, 2)
        finding, = json.loads(out)
        self.assertEqual(finding['rule'], 'documented-image-denoising-claim-false')
        self.assertEqual(finding['severity'], 'HIGH')
        self.assertEqual(finding['verdict'], 'FAIL')
        self.assertTrue(finding['message'])

    def test_test_only(self):
        root = self.fixture({'tests/fixture.md': POSITIVE[0]})
        status, out, _ = self.cli('audit', root, '--json')
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)[0]['severity'], 'MEDIUM')
        self.assertEqual(self.cli('audit', root, '--fail-on', 'medium')[0], 2)

    def test_denial(self):
        root = self.fixture({'README.md': NEGATIVE[0], 'app.py': 'x.denoise_image(data)'})
        status, out, _ = self.cli('audit', root, '--json')
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(out)[0]['rule'], 'documented-no-image-denoising-claim-false')
        self.assertEqual(json.loads(out)[0]['severity'], 'HIGH')

    def test_denial_no_source(self):
        self.assertEqual(self.cli('audit', self.fixture({'README.md': NEGATIVE[0]}))[:2], (0, 'PASS\n'))

    def test_no_claim(self):
        self.assertEqual(self.cli('audit', self.fixture({'README.md': 'Hello'}))[:2], (0, 'PASS\n'))

    def test_docs_and_collapse(self):
        root = self.fixture({'README.md': POSITIVE[0]*3, 'docs/nested/a.md': POSITIVE[1]})
        self.assertEqual(len(scan(root)), 1)
        self.assertEqual(scan(root)[0]['severity'], 'HIGH')

    def test_docs_nested(self):
        root = self.fixture({'docs/nested/a.md': POSITIVE[0], 'other.md': NEGATIVE[0]})
        self.assertEqual(scan(root)[0]['severity'], 'HIGH')

    def test_ignore(self):
        root = self.fixture({'docs/a.md': POSITIVE[0], 'tests/a.txt': POSITIVE[0]})
        self.assertEqual(self.cli('audit', root, '--ignore', 'docs/', '--ignore', 'tests/')[0], 0)

    def test_ignore_before_repo(self):
        root = self.fixture({'docs/a.md': POSITIVE[0]})
        self.assertEqual(self.cli('audit', '--ignore', 'docs/', root)[:2], (0, 'PASS\n'))

    def test_version(self):
        self.assertEqual(self.cli('--version')[:2], (0, '0.1.0\n'))

    def test_help(self):
        self.assertEqual(self.cli('--help')[0], 0)

    def test_errors(self):
        for args in ([], ['bogus'], ['audit', '--fail-on', 'low'], ['audit', '/nonexistent-repository']):
            self.assertEqual(self.cli(*args)[0], 1)

    def test_verbose_and_invalid_python(self):
        root = self.fixture({'README.md': POSITIVE[0], 'bad.py': 'def :', 'other.txt': 'x'})
        status, out, err = self.cli('audit', root, '--verbose', '--json')
        self.assertEqual(status, 2)
        self.assertIn('Scope:', err)
        self.assertIn('Invalid Python skipped: bad.py', err)
        self.assertIn('Outside scope: other.txt', err)
        json.loads(out)

    def test_exclusions(self):
        for directory in ('.git', '__pycache__', '.venv', 'venv', 'custom-env'):
            files = {'README.md': POSITIVE[0], directory+'/app.py': 'x.denoise_image(data)'}
            if directory == 'custom-env':
                files[directory+'/pyvenv.cfg'] = 'home = /tmp'
            self.assertEqual(scan(self.fixture(files))[0]['severity'], 'HIGH')

    def test_readme_self_audit(self):
        root = Path(__file__).resolve().parents[1]
        text = (root/'README.md').read_text(encoding='utf-8')
        self.assertEqual(claims(text), ([], []))
        self.assertEqual(self.cli('audit', self.fixture({'README.md': text}))[:2], (0, 'PASS\n'))

    def test_default_directory(self):
        import os
        old = Path.cwd()
        root = self.fixture({'README.md': 'Hello'})
        try:
            os.chdir(root)
            self.assertEqual(self.cli('audit')[:2], (0, 'PASS\n'))
        finally:
            os.chdir(old)


# Separate tests for every name and call form make the inventory coverage visible.
def route_test(source):
    def test(self):
        self.assertTrue(evidence(source))
    return test

for family, inventory in (('direct', DIRECT), ('generic', GENERIC)):
    for name in inventory:
        for form, source in (
            ('attribute', 'obj.'+name+'(data)'),
            ('chained', 'obj.child.'+name+'(data)'),
            ('imported', 'from lib import '+name+'\n'+name+'(data)'),
            ('alias', 'from lib import '+name+' as f\nf(data)'),
            ('module_alias', 'import lib as x\nx.'+name+'(data)'),
        ):
            setattr(AuditTests, 'test_'+family+'_'+name+'_'+form, route_test(source))

REJECTED = {
    'imports': 'import cv2, skimage, scipy, bm3d',
    'gaussian': 'cv2.GaussianBlur(data, (3,3), 0)',
    'pil_gaussian': 'PIL.ImageFilter.GaussianBlur(3)',
    'median': 'cv2.medianBlur(data, 3)',
    'box': 'cv2.blur(data, (3,3))',
    'unsharp': 'PIL.ImageFilter.UnsharpMask()',
    'kernel': 'cv2.filter2D(data, -1, kernel)',
    'super_resolution': 'upscaler.enhance(data)',
    'resize': 'img.resize((2,2))',
    'crop': 'img.crop((0,0,2,2))',
    'conversion': 'img.convert("RGB")',
    'audio': 'noisereduce.reduce_noise(y=data, sr=16000)',
    'rnnoise': 'RNNoise().process(data)',
    'inpaint': 'cv2.inpaint(data, mask, 3, 0)',
    'strings': '"""image denoising; image denoiser"""\nx="obj.denoise_image(data)"',
    'comment': '# obj.denoise_image(data)',
    'reference': 'from lib import denoise_image\nf = denoise_image',
    'subprocess': 'subprocess.run(["image-denoising", "input.png"])',
    'unbound': 'denoise_image(data)',
    'unbound_direct': 'fastNlMeansDenoising(data)',
    'bare_module': 'import bm3d\nbm3d(data)',
}
for label, source in REJECTED.items():
    def test(self, source=source):
        self.assertFalse(evidence(source))
    setattr(AuditTests, 'test_reject_'+label, test)

if __name__ == '__main__':
    unittest.main()
