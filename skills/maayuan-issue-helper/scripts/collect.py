"""Bounded, read-only MaaYuan evidence collection. Standard library only."""
import argparse
import codecs
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import uuid
import zipfile

MIB = 1024 * 1024
STAMP = re.compile(r'^\[?(\d{4}-\d{2}-\d{2})[ T]')
VERSION = re.compile(r'(MFA version|Resource version|MaaFramework version|\.NET version)\s*:\s*(.{1,100})', re.I)
SECRET = re.compile(r'''(?ix)(["']?(?:[\w.-]*(?:token|password|passwd|secret|api[_-]?key|authorization|cookie|cdk)[\w.-]*|uid|account|username|email|phone|serial|device_id|账号|帐号|密码|昵称|令牌|密钥)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;\]}]+)''')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def linked(path):
    """Reject symlinks and Windows junction/reparse points."""
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def safe_file(path, root):
    path = Path(path)
    path.relative_to(root)
    for item in [path, *path.parents]:
        if linked(item):
            raise ValueError('linked_path')
        if item == root:
            break
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('outside_root_or_not_file')
    return path


def redact(text, root=None):
    if root:
        # Includes JSON-escaped Windows paths.
        for value in sorted({str(root), str(root).replace('\\', '/'), str(root).replace('\\', '\\\\')}, key=len, reverse=True):
            text = re.sub(re.escape(value), '<MAAYUAN_DIR>', text, flags=re.I)
    text = re.sub(r'(?i)\bBearer\s+[^\s"\',;\]}]+', 'Bearer <REDACTED>', text)
    text = re.sub(r'(?i)((?:authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+', r'\1<REDACTED>', text)
    text = SECRET.sub(lambda m: m[1] + '"<REDACTED>"', text)
    text = re.sub(r'(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,})\b', '<SECRET>', text)
    text = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '<JWT>', text)
    text = re.sub(r'(?i)https?://[^\s<>"\']+', '<URL_REDACTED>', text)
    text = re.sub(r'(?i)[A-Z]:[\\/]+[^\r\n"<>|]*', '<LOCAL_PATH>', text)
    text = re.sub(r'(?i)/(?:Users|home)/[^\s/"<>]+', '/<USER_HOME>', text)
    text = re.sub(r'\\\\[^\s"<>]+', '<UNC_PATH>', text)
    text = re.sub(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '<EMAIL>', text)
    text = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '<PHONE>', text)
    text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '<IP>', text)
    text = re.sub(r'(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b', '<MAC>', text)
    return text


def decode_sample(path, maximum):
    # Bounded read even for a single gigantic line. Never load the entire disk file.
    with path.open('rb') as handle:
        raw = handle.read(maximum + 1)
    cut = len(raw) > maximum
    raw = raw[:maximum]
    encodings = ['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'gb18030']
    for encoding in encodings:
        try:
            decoder = codecs.getincrementaldecoder(encoding)(errors='strict')
            text = decoder.decode(raw, final=not cut)
            if '\x00' in text:
                continue
            # Remove incomplete final line after a capped read.
            if cut:
                text = text.rsplit('\n', 1)[0] if '\n' in text else ''
            return text, encoding, cut
        except UnicodeError:
            continue
    raise ValueError('undecodable_or_binary')


def candidates(root, date):
    result, omitted = [], []
    groups = [('logs', 'log-*.log'), ('debug', 'maa*.log'), ('debug/custom', '*.log')]
    for folder, pattern in groups:
        base = root / folder
        if not base.exists():
            omitted.append({'source': folder, 'reason': 'directory_missing'})
            continue
        # Validate every directory component before enumeration.
        if any(linked(p) for p in [base, *list(base.parents)[:len(Path(folder).parts) - 1]]):
            omitted.append({'source': folder, 'reason': 'linked_directory_excluded'})
            continue
        paths = list(base.glob(pattern))
        if folder == 'debug':
            paths = [p for p in paths if p.name in ('maa.log', 'maa.bak.log')]
        valid = []
        for path in paths:
            name = path.relative_to(root).as_posix()
            try:
                safe_file(path, root)
                if date and folder != 'debug' and date not in path.name and date.replace('-', '') not in path.name:
                    omitted.append({'source': name, 'reason': 'other_date_filename'})
                    continue
                valid.append(path)
            except (OSError, ValueError):
                omitted.append({'source': name, 'reason': 'unsafe_or_unreadable'})
        valid.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        limit = 10 if date else 2
        result.extend(valid[:limit])
        omitted.extend({'source': p.relative_to(root).as_posix(), 'reason': 'file_count_limit'} for p in valid[limit:])
    return result, omitted


def collect(args):
    root = Path(args.root).absolute()
    if not root.is_dir() or linked(root):
        raise ValueError('root must be an existing ordinary directory')
    root = root.resolve()
    if not (root / 'interface.json').is_file():
        raise ValueError('interface.json missing; select the MaaYuan application directory')
    out = Path(args.out).absolute()
    if out.resolve() == root or root.is_relative_to(out.resolve()):
        raise ValueError('output cannot contain or replace source directory')
    # An existing output is always refused; no stale bundle mixing.
    out.mkdir(parents=True, exist_ok=False)
    paths, omitted = candidates(root, args.date)
    records, observed = [], []
    remaining = args.max_total_mib * MIB
    for path in paths:
        rel = path.relative_to(root).as_posix()
        record = {'source': rel}
        records.append(record)
        if remaining <= 0:
            record['status'] = 'total_limit_excluded'
            continue
        try:
            before = path.stat()
            text, encoding, scan_cut = decode_sample(path, args.max_scan_mib * MIB)
            day, lines, used, output_cut, first, last = None, [], 0, False, None, None
            for number, line in enumerate(text.splitlines(), 1):
                stamp = STAMP.match(line)
                if stamp:
                    day = stamp[1]
                if args.date and day != args.date:
                    continue
                cleaned = redact(line, root)
                entry = f'L{number}\t{cleaned}\n'
                size = len(entry.encode('utf-8'))
                if used + size > min(args.max_file_mib * MIB, remaining):
                    output_cut = True
                    break
                lines.append(entry)
                used += size
                first = number if first is None else first
                last = number
                version = VERSION.search(cleaned)
                if version and len(observed) < 100:
                    observed.append({'label': version[1], 'value': version[2], 'source': rel, 'line': number, 'log_date': day})
            after = path.stat()
            record.update(encoding=encoding, source_bytes=before.st_size,
                          modified_at=datetime.fromtimestamp(before.st_mtime).astimezone().isoformat(),
                          scan_truncated=scan_cut, output_truncated=output_cut,
                          changed_during_read=(before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns),
                          first_source_line=first, last_source_line=last, exported_lines=len(lines))
            if not lines:
                record['status'] = 'no_matching_lines_in_scanned_range'
                continue
            target = out / 'logs' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('w', encoding='utf-8', newline='') as handle:
                handle.write(''.join(lines))
            remaining -= used
            record.update(status='included', export=target.relative_to(out).as_posix(), exported_bytes=used)
        except (OSError, ValueError) as exc:
            # Do not emit exception messages containing local paths or log contents.
            record.update(status='read_failed', error_type=type(exc).__name__)
    current_version = None
    try:
        interface = safe_file(root / 'interface.json', root)
        if interface.stat().st_size <= 8 * MIB:
            value = json.loads(interface.read_text(encoding='utf-8-sig')).get('version')
            if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9.+_-]{1,80}', value):
                current_version = value
    except (OSError, ValueError):
        pass
    report_id = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    manifest = {'schema_version': 1, 'report_id': report_id,
                'collected_at': datetime.now().astimezone().isoformat(),
                'selection': {'date': args.date, 'no_date_policy': 'two_newest_per_family',
                              'max_file_mib': args.max_file_mib, 'max_total_mib': args.max_total_mib,
                              'max_scan_mib': args.max_scan_mib},
                'files': records, 'excluded': omitted,
                'privacy': 'Rule-based redaction only; review before sharing. No configs or images included.'}
    metadata = {'current_resource_version': current_version, 'version_source': 'interface.json:version',
                'observed_runtime_versions': observed,
                'collection_host': {'os': platform.system(), 'release': platform.release(), 'architecture': platform.machine()},
                'note': 'Collection host may differ from fault host. Log versions describe historical runs.'}
    write_json(out / 'manifest.json', manifest)
    write_json(out / 'metadata.json', metadata)
    (out / 'forum-post.txt').write_text('【草稿：需 AI 根据用户描述与日志完成】\n问题：待补充\n发生时间：待补充\n预期与实际：待补充\n日志事实：待分析\n初步判断：尚无法确定\n附件：本地已采集，尚未上传\n', encoding='utf-8')
    (out / 'report.md').write_text('# 故障报告草稿\n\n报告 ID：' + report_id + '\n\n请按 references/report-format.md 完成报告。采集成功不表示已完成分析。\n', encoding='utf-8')
    (out / 'SHARING.txt').write_text('发布前复核正文和日志。规则脱敏不保证识别全部隐私。\n本包不含配置、截图和游戏数据，截断及缺失见 manifest.json。\n本地采集不等于已提交，不代表维护者承诺处理。\n尝试修复前复制完整程序目录，在副本修改；更新可能覆盖修改或产生兼容问题。\n', encoding='utf-8')
    return {'bundle': str(out), 'included': sum(r.get('status') == 'included' for r in records), 'report_id': report_id, 'next': 'Analyze logs, finish and review both reports, then run pack.'}


def pack(args):
    base = Path(args.bundle).absolute()
    if linked(base):
        raise ValueError('linked bundle refused')
    base = base.resolve()
    manifest_path = safe_file(base / 'manifest.json', base)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    names = ['manifest.json', 'metadata.json', 'forum-post.txt', 'report.md', 'SHARING.txt']
    for item in manifest['files']:
        if item.get('status') == 'included':
            name = item['export']
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or not name.startswith('logs/') or relative.suffix != '.log':
                raise ValueError('invalid manifest export')
            names.append(name)
    if len(set(names)) != len(names):
        raise ValueError('duplicate bundle member')
    payloads = {}
    total = 0
    for name in names:
        path = safe_file(base / name, base)
        if path.stat().st_size > 128 * MIB:
            raise ValueError('bundle member too large')
        content = path.read_bytes()
        total += len(content)
        if total > 256 * MIB:
            raise ValueError('bundle exceeds 256 MiB')
        payloads[name] = content
    manifest['packed_at'] = datetime.now().astimezone().isoformat()
    # The manifest itself is deliberately excluded from its own hashes.
    manifest['sha256'] = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items() if name != 'manifest.json'}
    payloads['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    target = base.with_name(base.name + '-' + uuid.uuid4().hex[:8] + '.zip')
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('archive verification failed')
    manifest_path.write_bytes(payloads['manifest.json'])
    return {'zip': str(target), 'members': len(payloads), 'bytes': target.stat().st_size}


def positive(value):
    number = int(value)
    if not 1 <= number <= 256:
        raise argparse.ArgumentTypeError('must be between 1 and 256 MiB')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    gather = sub.add_parser('collect')
    gather.add_argument('--root', required=True)
    gather.add_argument('--out', required=True)
    gather.add_argument('--date', help='YYYY-MM-DD, log-local date')
    gather.add_argument('--max-file-mib', type=positive, default=4)
    gather.add_argument('--max-total-mib', type=positive, default=24)
    gather.add_argument('--max-scan-mib', type=positive, default=64)
    bundle = sub.add_parser('pack')
    bundle.add_argument('--bundle', required=True)
    args = parser.parse_args()
    if args.command == 'collect' and args.date:
        try:
            datetime.strptime(args.date, '%Y-%m-%d')
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.date):
                raise ValueError()
        except ValueError:
            parser.error('--date must be YYYY-MM-DD')
    try:
        result = collect(args) if args.command == 'collect' else pack(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error_type': type(exc).__name__, 'message': 'Operation failed; check input paths, permissions and bundle format. No source files were modified.'}))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
