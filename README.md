# Documentation claim auditor

Version 0.1.0. An offline, deterministic, standard-library-only checker for
claims about removing noise from a still picture. Requires Python 3.9 or newer.
No network, telemetry, LLM, or filesystem writes.

## Installation and usage

```sh
python3 -m pip install .
image-denoising-claim-audit --version
python3 -m image_denoising_claim_audit --help
image-denoising-claim-audit audit . --json --verbose
image-denoising-claim-audit audit --ignore tests/ . --fail-on medium
```

The repository defaults to the current directory. Each ignore option accepts
one relative path prefix and can be repeated. JSON emits an array with rule,
severity, verdict, and message fields. Verbose decisions go to standard error.
Exit status is 0 when no finding meets the threshold, 2 when one does, and 1
for usage or IO errors. The default threshold is high; medium also fails
findings confined to test fixtures.

## Scope

The root README and Markdown files beneath docs supply documentation claims.
Fenced code is excluded; inline code retains its text. Files beneath a tests
directory supply lower-severity positive claims only. Each rule family emits
at most one finding. A denial without contradictory source evidence passes.

```text
documented-image-denoising-claim-false (HIGH; test-only: MEDIUM)
documented-no-image-denoising-claim-false (HIGH)
```

Python sources are scanned recursively, excluding Git metadata, bytecode
caches, and virtual environments. A single recognized call suffices in one
module. Imported bare calls and aliases are resolved; attribute calls accept
any base. Local function and class definitions shadow matching imports
throughout that module. Imports alone, references, comments, strings, external
commands, and evidence assembled across modules do not establish the feature.
Invalid Python is skipped with a verbose diagnostic.

## Differentiation

These neighboring tools check distinct capabilities, in the order listed:

```text
noise-suppression-claim-audit
super-resolution-claim-audit
image-generation-claim-audit
```

The first checks removing noise from audio; this checker concerns a still
picture. The second checks enlarging an image with a model; this checker
concerns removing noise from it. The third checks creating new images;
this checker concerns cleaning existing ones.

## Limitations

Static pattern matching cannot provide semantic judgement or verify runtime
behavior. Only exact phrases match, ignoring case; restatements do not match.
Hyphens are preserved. Denial spans are removed before positive matching.
Longest-first matching blanks each span, so each occurrence matches once
under its longest phrase.

A Gaussian blur call deliberately does not count because smoothing is not
removing noise. Sharpening, enlarging, resizing, cropping, format conversion,
audio processing, and filling missing regions alone also do not count.
An unrelated object with this shared method name counts via the generic
route, which can supply false evidence:

```python
unrelated.denoise_image(data)
```

These exact phrases also describe cleaning scanned photos by hand and a
school exercise, respectively. The checker cannot infer the intended meaning:

```text
denoise images by hand before printing
photo denoising worksheet
```

Another substring collision matches the checked capability even when the
surrounding words suggest organizing files:

```text
denoise image files by date
```

Dynamic dispatch, wrappers, and unsupported names can hide real capability.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

The source distribution bundles the discoverable test suite. Licensed under MIT.
