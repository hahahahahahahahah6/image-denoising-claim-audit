"""Read-only, module-local static documentation audit."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import sys

from . import __version__
from .phrases import IMAGEDENOISING, NOIMAGEDENOISING, DIRECT_NAMES, GENERIC_NAMES


def match_phrases(text, phrases):
    """Return longest nonoverlapping matches and the remaining text."""
    text = text.lower()
    found = []
    for phrase in sorted(phrases, key=len, reverse=True):
        while phrase in text:
            start = text.index(phrase)
            found.append(phrase)
            text = text[:start] + ' ' * len(phrase) + text[start + len(phrase):]
    return found, text


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append('')
        else:
            lines.append('' if fence else line)
    prose = '\n'.join(lines).replace('`', '')
    negative, rest = match_phrases(prose, NOIMAGEDENOISING)
    positive, _ = match_phrases(rest, IMAGEDENOISING)
    return positive, negative


def evidence(source):
    """Recognize calls; imports and definitions never cross module boundaries."""
    tree = ast.parse(source)
    aliases = {}
    shadowed = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadowed.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    names = set(DIRECT_NAMES + GENERIC_NAMES)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
            base = func.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id in shadowed:
                continue
            if name in names and name not in shadowed:
                return True
        elif isinstance(func, ast.Name):
            name = aliases.get(func.id)
            if func.id not in shadowed and name in names and name not in shadowed:
                return True
    return False


POSITIVE_RULE = 'documented-image-denoising-claim-false'
NEGATIVE_RULE = 'documented-no-image-denoising-claim-false'
EXCLUDED = {'.git', '__pycache__', '.venv', 'venv', 'env', '.env', 'virtualenv'}


def scan(repo, ignore=(), verbose=False):
    root = Path(repo)
    if not root.is_dir():
        raise OSError('Repository is not a directory: ' + str(root))
    documented = False
    denied = False
    test_claim = False
    supported = False

    def log(message):
        if verbose:
            print(message, file=sys.stderr)

    def walk_error(error):
        raise error

    log('Scope: README.md, docs/**/*.md, tests fixtures, and Python sources in ' + str(root))
    for directory, dirs, files in os.walk(root, onerror=walk_error):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (base / d / 'pyvenv.cfg').is_file()
                         and not any((base / d).relative_to(root).as_posix().startswith(x) for x in ignore))
        for filename in sorted(files):
            path = base / filename
            rel = path.relative_to(root).as_posix()
            if any(rel.startswith(prefix) for prefix in ignore):
                log('Skipped prefix: ' + rel)
                continue
            is_test = 'tests' in path.relative_to(root).parts[:-1]
            doc = rel == 'README.md' or (rel.startswith('docs/') and path.suffix == '.md')
            if not (doc or is_test or path.suffix == '.py'):
                log('Outside scope: ' + rel)
                continue
            text = path.read_text(encoding='utf-8')
            if doc or is_test:
                yes, no = claims(text)
                if doc:
                    documented |= bool(yes)
                    denied |= bool(no)
                elif is_test:
                    test_claim |= bool(yes)
                log('Claims ' + rel + ': positive=' + str(bool(yes)) + ', negative=' + str(bool(no)))
            if path.suffix == '.py':
                try:
                    result = evidence(text)
                except SyntaxError:
                    log('Invalid Python skipped: ' + rel)
                else:
                    supported |= result
                    log('Evidence ' + rel + ': ' + str(result))
    findings = []
    if not supported and (documented or test_claim):
        findings.append(dict(rule=POSITIVE_RULE, severity='HIGH' if documented else 'MEDIUM',
                             verdict='FAIL', message='A documented capability has no matching source call.'))
    if denied and supported:
        findings.append(dict(rule=NEGATIVE_RULE, severity='HIGH', verdict='FAIL',
                             message='A documented denial contradicts a matching source call.'))
    return findings


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(prog='image-denoising-claim-audit')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    audit = commands.add_parser('audit')
    audit.add_argument('repo', nargs='?', default='.')
    audit.add_argument('--json', action='store_true')
    audit.add_argument('--verbose', action='store_true')
    audit.add_argument('--ignore', action='append', default=[], metavar='PREFIX')
    audit.add_argument('--fail-on', choices=('high', 'medium'), default='high')
    try:
        args = parser.parse_args(argv)
        findings = scan(args.repo, args.ignore, args.verbose)
    except SystemExit as error:
        return error.code
    except (OSError, UnicodeError) as error:
        print('error: ' + str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(findings, indent=2))
    elif findings:
        for finding in findings:
            print('{severity} {rule}: {message}'.format(**finding))
    else:
        print('PASS')
    return 2 if any(f['severity'] == 'HIGH' or args.fail_on == 'medium' for f in findings) else 0
