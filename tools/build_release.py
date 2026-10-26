"""Build shareable skill/source ZIP files from an explicit source allowlist."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/maayuan-issue-helper'
VERSION = '0.1.0'
SKILL_FILES = ['SKILL.md', 'scripts/collect.py', 'references/maayuan-logs.md', 'references/report-format.md']
REPO_FILES = ['README.md', 'LICENSE', '.gitignore', 'docs/design.md', 'docs/community-proposal.md',
              'tests/test_collect.py', 'tools/build_release.py']


def make_zip(target, files):
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None


def main():
    dest = ROOT / 'downloads'
    dest.mkdir(exist_ok=True)
    skill_zip = dest / f'maayuan-issue-helper-skill-v{VERSION}.zip'
    source_zip = dest / f'maayuan-issue-helper-source-v{VERSION}.zip'
    make_zip(skill_zip, [(SKILL / name, name) for name in SKILL_FILES] + [(ROOT / 'LICENSE', 'LICENSE')])
    paths = REPO_FILES + ['skills/maayuan-issue-helper/' + name for name in SKILL_FILES]
    make_zip(source_zip, [(ROOT / name, 'maayuan-issue-helper/' + name) for name in paths])
    (dest / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n' for path in [skill_zip, source_zip]), encoding='utf-8')
    for path in [skill_zip, source_zip, dest / 'SHA256SUMS.txt']:
        print(path)


if __name__ == '__main__':
    main()
