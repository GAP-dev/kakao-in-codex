"""Build a source release from a fixed set of repository files."""
import argparse
import hashlib
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    '.dockerignore', '.gitignore', '.gitattributes', '.editorconfig',
    'README.md', 'CONTRIBUTING.md', 'CHANGELOG.md', 'NOTICE.md', 'LICENSE',
    'Dockerfile', 'compose.yaml', 'container-entrypoint.sh', 'kakao',
    'requirements.txt', 'requirements-dev.txt', 'ssh-command.py', 'sshd_config',
}
DIRECTORIES = {'bridge', 'scripts', 'tests', 'docs', '.github'}
SKIP = {'__pycache__', '.pytest_cache', '.venv', 'secrets', '.git', 'dist'}
PRIVATE_KEY = re.compile(rb'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----')


def sources():
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if any(part in SKIP for part in relative.parts):
            continue
        if relative.as_posix() not in FILES and relative.parts[0] not in DIRECTORIES:
            continue
        if path.is_symlink():
            raise ValueError(f'Symlinks cannot be packaged: {relative}')
        if not path.is_file() or path.suffix in {'.pyc', '.log', '.pid', '.zip'}:
            continue
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError(f'File outside repository: {relative}')
        data = path.read_bytes()
        if PRIVATE_KEY.search(data):
            raise ValueError(f'Private key found: {relative}')
        yield relative, data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', args.version):
        parser.error('version must look like v0.1.0 or v0.1.0-beta.1')
    entries = list(sources())
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f'kakao-bridge-{args.version}'
    archive = args.output / f'{stem}.zip'
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        for relative, data in entries:
            info = ZipInfo(f'{stem}/{relative.as_posix()}', date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o100755 if relative.name in {'kakao', 'container-entrypoint.sh'} else 0o100644) << 16
            bundle.writestr(info, data)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.output / f'{stem}.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
    print(f'{archive.name}: {len(entries)} files')


if __name__ == '__main__':
    main()
