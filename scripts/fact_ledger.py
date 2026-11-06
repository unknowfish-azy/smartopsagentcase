"""FCT-P0-01 事实台账生成器（只读）。

统计口径全部给出定义，缺失统计源写 null + 原因，不猜数、不批量替换文档。
输出：metrics.json / fact-sheet.md / sources.json / stale-claims.md / run-meta.json

确定性：metrics.json 不含时间戳；生成时间单独写 run-meta.json。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / 'docs/development/fct-p0-01-evidence'
SCHEMA_VERSION = 1

JAVA_MAIN_ROOT = 'backend/src/main/java'
JAVA_TEST_ROOT = 'backend/src/test/java'
VUE_ROOT = 'frontend/src'
MIGRATION_ROOT = 'backend/src/main/resources/db/migration'
CLAIM_SCAN_ROOT = 'docs'
# 对外材料范围：赛事/审计目录与 docs 顶层说明文；docs/development 是本流程的工作报告，不参与主张核对。
CLAIM_SCAN_DIRS = ('docs/competition', 'docs/audit')

MAPPING_RE = re.compile(
    r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)'
)
TEST_ANNOTATION_RE = re.compile(r'@Test\b')
CREATE_TABLE_RE = re.compile(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"]?(\w+)', re.IGNORECASE)

# 待核对数字：来自任务书 §3 与旧材料的高频口径
CLAIM_NUMBERS = [219, 17981, 80, 296, 146, 563, 79, 83, 541, 113, 135, 428, 81, 111, 89, 501, 205]
HISTORICAL_MARKERS = ('历史', '旧稿', '旧材料', '此前', '曾为', '曾经', '上一轮', '修订前', '原为', '历史快照', '旧数值', '旧版')
CURRENT_MARKERS = ('当前', '现状', '本轮', '截至', '现在是', '现在为', '现有')

DEFINITIONS = {
    'java.main.file_n': 'backend/src/main/java 下 *.java 文件数（递归，不含 target/）',
    'java.main.loc.total': '总行数，含空行与注释行',
    'java.main.loc.blank': '去掉首尾空白后为空的行数',
    'java.main.loc.comment': '整行仅注释（//、/* */），无代码字符的行数',
    'java.main.loc.code': '非空且含至少一个代码字符的行数',
    'java.main => code + comment + blank = total': '恒等式，用于自检',
    'java.routes.route_annotation_n': 'GetMapping/PostMapping/PutMapping/DeleteMapping/PatchMapping/RequestMapping 注解出现次数（含类级）',
    'java.routes.actual_route_n': '类级 @RequestMapping 基路径 + 方法级注解路径组合后的 (HTTP方法, 路径) 去重数',
    'java.routes.unresolved_annotation_n': '路径不是字符串字面量（常量/变量拼接）而无法静态解析的方法级注解数，不静默丢弃',
    'java.test.file_n': 'backend/src/test/java 下 *.java 文件数',
    'java.test.test_annotation_n': '@Test 注解出现次数（一个类可有多个；不等于用例执行数）',
    'java.main.controller_file_n': '文件名含 Controller 的 Java 文件数',
    'java.main.service_file_n': '文件名以 Service 结尾的 Java 文件数',
    'vue.file_n': 'frontend/src 下 *.vue 文件数',
    'vue.loc.*': '同上 LOC 口径（Vue 单文件按整文件计，识别 <!-- --> 注释）',
    'migrations.file_n': 'backend/src/main/resources/db/migration 下 *.sql 文件数（不含 target/ 副本）',
    'migrations.create_table_n': '上述 migration 文件中 CREATE TABLE 语句数（含 IF NOT EXISTS）',
    'migrations.offline_distinct_table_n': '上述 CREATE TABLE 的目标表名去重数（离线定义口径，不是运行库事实）',
    'migrations.runtime_tables_n': '运行库实际表数；未连接数据库时为 null，原因见 unavailable',
    'tests.pytest.collected_n': 'pytest --collect-only 收集到的用例数（本快照、本解释器）',
    'tests.pytest.executed_n': '解析 junitxml 得到的执行数；未提供 junitxml 时为 null',
    'tests.pytest.junitxml_sha256': 'junitxml 原始日志的 sha256，用于把执行/通过/跳过数追回到原始日志',
    'sources.*': '被统计文件的 sha256 与字节数，用于追溯单个数字',
    'snapshot.source_digest': '按路径排序的 "path<TAB>sha256" 拼接后再 sha256，用于“同一快照重复生成一致”的比较',
}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def rel_posix(path: Path) -> str:
    return path.as_posix().replace(str(REPO_ROOT.as_posix()) + '/', '')


def iter_files(root: Path, pattern: str):
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob(pattern) if p.is_file())


def count_lines(text: str, *, html_comments: bool = False) -> dict[str, int]:
    """按行分类 total / blank / comment / code。识别字符串状态，避免把字符串里的 // 当注释。"""
    total = blank = comment = code = 0
    state = 'normal'  # normal|line|block|html|dq|sq|tpl
    has_code = has_any = False

    def finish_line():
        nonlocal total, blank, comment, code, has_code, has_any
        total += 1
        if not has_any:
            blank += 1
        elif has_code:
            code += 1
        else:
            comment += 1
        has_code = has_any = False

    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '\n':
            if state == 'line':
                state = 'normal'
            finish_line()
            i += 1
            continue
        has_any = True
        if state == 'normal':
            if text.startswith('//', i):
                state = 'line'; i += 2; continue
            if text.startswith('/*', i):
                state = 'block'; i += 2; continue
            if html_comments and text.startswith('<!--', i):
                state = 'html'; i += 4; continue
            if ch == '"':
                state = 'dq'; has_code = True; i += 1; continue
            if ch == "'":
                state = 'sq'; has_code = True; i += 1; continue
            if ch == '`':
                state = 'tpl'; has_code = True; i += 1; continue
            if not ch.isspace():
                has_code = True
            i += 1; continue
        if state == 'line':
            i += 1; continue
        if state == 'block':
            if text.startswith('*/', i):
                state = 'normal'; i += 2; continue
            i += 1; continue
        if state == 'html':
            if text.startswith('-->', i):
                state = 'normal'; i += 3; continue
            i += 1; continue
        if state == 'dq':
            has_code = True
            if ch == '\\':
                i += 2; continue
            if ch == '"':
                state = 'normal'
            i += 1; continue
        if state == 'sq':
            has_code = True
            if ch == '\\':
                i += 2; continue
            if ch == "'":
                state = 'normal'
            i += 1; continue
        # tpl
        has_code = True
        if ch == '\\':
            i += 2; continue
        if ch == '`':
            state = 'normal'
        i += 1
    if text and not text.endswith('\n'):
        finish_line()
    return {'total': total, 'blank': blank, 'comment': comment, 'code': code}


# ---------------------------------------------------------------------------
# Java 路由解析
# ---------------------------------------------------------------------------

def _read_balanced(text: str, start: int) -> tuple[str, int]:
    """从 '(' 之后开始读取，返回括号内文本与结束位置（消费到匹配的 ')'）。"""
    depth = 1
    i = start
    out = []
    while i < len(text) and depth > 0:
        ch = text[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                i += 1
                break
        out.append(ch)
        i += 1
    return ''.join(out), i


def _split_top_level(args: str) -> list[str]:
    parts, buf, depth, in_str = [], [], 0, False
    for ch in args:
        if in_str:
            buf.append(ch)
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True; buf.append(ch); continue
        if ch in '({[':
            depth += 1
        elif ch in ')}]':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(buf)); buf = []; continue
        buf.append(ch)
    tail = ''.join(buf).strip()
    if tail:
        parts.append(''.join(buf))
    return parts


def _string_literals(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', text)]


NON_PATH_ATTRS = {'produces', 'consumes', 'headers', 'params', 'name'}


def _path_segments(args: str) -> list[str]:
    """返回可能是路径的参数片段（排除 produces/consumes 等具名属性）。"""
    segments = []
    for segment in _split_top_level(args):
        if '=' in segment:
            attr = segment.partition('=')[0].strip()
            if attr in NON_PATH_ATTRS or attr == 'method':
                continue
            segments.append(segment)
        else:
            segments.append(segment)
    return segments


def _paths_from_args(args: str) -> list[str]:
    """从注解参数里提取路径字面量。positional 或 value=/path= 视为路径，其余具名属性跳过。"""
    if not args.strip():
        return []
    paths: list[str] = []
    for segment in _path_segments(args):
        if '=' in segment:
            paths.extend(_string_literals(segment.partition('=')[2]))
        else:
            paths.extend(_string_literals(segment))
    return paths


def _has_unresolved_expression(args: str) -> bool:
    """参数里存在非字面量的路径表达式（常量拼接），静态无法解析。"""
    segments = _path_segments(args)
    return any(not _string_literals(segment) for segment in segments)


def _http_method(annotation: str, args: str) -> str:
    if annotation != 'RequestMapping':
        return annotation.replace('Mapping', '').upper()
    found = re.findall(r'RequestMethod\.\w+', args)
    if found:
        return '|'.join(item.split('.')[-1].upper() for item in found)
    return 'ANY'


def scan_java_routes(text: str) -> dict:
    annotations = []
    for m in MAPPING_RE.finditer(text):
        cursor = m.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        args = ''
        if cursor < len(text) and text[cursor] == '(':
            args, _ = _read_balanced(text, cursor + 1)
        annotations.append({'annotation': m.group(1), 'args': args, 'start': m.start(),
                            'end': cursor})

    class_pos = text.find(' class ')
    class_base, routes, unresolved, class_idx = '', [], 0, -1
    if class_pos >= 0:
        before = [a for a in annotations if a['start'] < class_pos]
        if before:
            class_idx = len(before) - 1
            class_base = (_paths_from_args(before[-1]['args']) or [''])[0]

    for idx, ann in enumerate(annotations):
        if idx == class_idx:
            continue
        if ann['annotation'] == 'RequestMapping' and ann['start'] < class_pos:
            continue
        paths = _paths_from_args(ann['args'])
        if not paths:
            if _has_unresolved_expression(ann['args']):
                unresolved += 1
                routes.append({'http': _http_method(ann['annotation'], ann['args']),
                               'path': '*UNRESOLVED*', 'line': text.count('\n', 0, ann['start']) + 1})
                continue
            # 空参数（如裸 @GetMapping）表示沿用类级基路径，不算无法解析。
            paths = ['']
        for path in paths:
            full = (class_base.rstrip('/') + '/' + path.lstrip('/')).rstrip('/') if class_base or path else ''
            full = full if full.startswith('/') or not full else '/' + full
            routes.append({'http': _http_method(ann['annotation'], ann['args']),
                           'path': full or '/', 'line': text.count('\n', 0, ann['start']) + 1})

    dedup = {(r['http'], r['path']) for r in routes}
    return {
        'route_annotation_n': len(annotations),
        'actual_route_n': len(dedup),
        'unresolved_annotation_n': unresolved,
        'routes': routes,
    }


# ---------------------------------------------------------------------------
# 各统计源
# ---------------------------------------------------------------------------

def collect_java(root_rel: str, *, with_routes: bool) -> dict:
    root = REPO_ROOT / root_rel
    files = iter_files(root, '*.java')
    if not root.is_dir():
        return {'file_n': None, 'loc': None, 'reason': f'统计源缺失：{root_rel}', 'files': []}
    loc = {'total': 0, 'blank': 0, 'comment': 0, 'code': 0}
    routes = {'route_annotation_n': 0, 'actual_route_n': 0, 'unresolved_annotation_n': 0, 'routes': []}
    test_annotations = 0
    entries = []
    for path in files:
        text = path.read_text(encoding='utf-8', errors='replace')
        counted = count_lines(text)
        for key in loc:
            loc[key] += counted[key]
        if with_routes:
            scanned = scan_java_routes(text)
            routes['route_annotation_n'] += scanned['route_annotation_n']
            routes['unresolved_annotation_n'] += scanned['unresolved_annotation_n']
            for route in scanned['routes']:
                routes['routes'].append({**route, 'controller': path.stem})
        test_annotations += len(TEST_ANNOTATION_RE.findall(text))
        entries.append({'path': rel_posix(path), 'sha256': sha256_bytes(path.read_bytes()),
                        'bytes': path.stat().st_size, 'loc': counted})
    if with_routes:
        routes['actual_route_n'] = len({(r['http'], r['path']) for r in routes['routes']})
    result = {'file_n': len(files), 'loc': loc, 'files': entries}
    if with_routes:
        result['routes'] = routes
        result['controller_file_n'] = sum(1 for path in files if 'Controller' in path.stem)
        result['service_file_n'] = sum(1 for path in files if path.stem.endswith('Service'))
    else:
        result['test_annotation_n'] = test_annotations
        result['test_class_n'] = len(files)
    return result


def collect_vue() -> dict:
    root = REPO_ROOT / VUE_ROOT
    files = iter_files(root, '*.vue')
    if not root.is_dir():
        return {'file_n': None, 'loc': None, 'reason': f'统计源缺失：{VUE_ROOT}', 'files': []}
    loc = {'total': 0, 'blank': 0, 'comment': 0, 'code': 0}
    entries = []
    for path in files:
        text = path.read_text(encoding='utf-8', errors='replace')
        counted = count_lines(text, html_comments=True)
        for key in loc:
            loc[key] += counted[key]
        entries.append({'path': rel_posix(path), 'sha256': sha256_bytes(path.read_bytes()),
                        'bytes': path.stat().st_size, 'loc': counted})
    return {'file_n': len(files), 'loc': loc, 'files': entries}


def collect_migrations() -> dict:
    root = REPO_ROOT / MIGRATION_ROOT
    files = iter_files(root, '*.sql')
    if not root.is_dir():
        return {'file_n': None, 'create_table_n': None, 'tables': [],
                'reason': f'统计源缺失：{MIGRATION_ROOT}', 'files': []}
    tables, entries = [], []
    for path in files:
        text = path.read_text(encoding='utf-8', errors='replace')
        for match in CREATE_TABLE_RE.finditer(text):
            tables.append({'table': match.group(1), 'file': path.name,
                           'line': text.count('\n', 0, match.start()) + 1})
        entries.append({'path': rel_posix(path), 'sha256': sha256_bytes(path.read_bytes()),
                        'bytes': path.stat().st_size})
    return {'file_n': len(files), 'create_table_n': len(tables),
            'offline_distinct_table_n': len({t['table'].lower() for t in tables}),
            'offline_tables': sorted({t['table'].lower() for t in tables}),
            'tables': tables, 'runtime_tables_n': None, 'files': entries}


def runtime_db_reason() -> dict:
    """运行库表数：优先用 mysql CLI；不存在则记 null 与原因，不猜。"""
    import shutil
    if not shutil.which('mysql'):
        return {'metric': 'migrations.runtime_tables_n', 'value': None,
                'reason': '未找到 mysql CLI，且未提供连接参数；不猜测运行库表数。'}
    return {'metric': 'migrations.runtime_tables_n', 'value': None,
            'reason': 'mysql CLI 存在但本任务未授权数据库连接；不访问生产/本地运行库。'}


def collect_pytest(collect: bool) -> dict:
    result = {'collected_n': None, 'executed_n': None, 'passed_n': None,
              'failed_n': None, 'skipped_n': None, 'error_n': None}
    reasons = []
    if collect:
        proc = subprocess.run(
            [sys.executable, '-m', 'pytest', 'tests', '--collect-only', '-q', '-p', 'no:cacheprovider'],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace',
        )
        match = re.search(r'^(\d+)\s+tests?\s+collected', proc.stdout, re.MULTILINE)
        if proc.returncode == 0 and match:
            result['collected_n'] = int(match.group(1))
        else:
            reasons.append(f'pytest --collect-only 失败（exit={proc.returncode}）')
    else:
        reasons.append('本轮以 --no-pytest-collect 运行：收集数为 null')
    result['reason'] = '；'.join(reasons) or None
    return result


def parse_junitxml(path: Path) -> dict:
    text = path.read_text(encoding='utf-8', errors='replace')
    head = re.search(r'<testsuite[^>]*?(?:\s+tests="(\d+)")?(?:\s+.*?errors="(\d+)")?', text)
    root_match = re.search(r'<testsuites[^>]*>', text)

    def attr(tag: str, name: str):
        m = re.search(rf'<{tag}[\s>][^>]*\b{name}="(\d+)"', text)
        return int(m.group(1)) if m else None

    counted = {name: attr('testsuite', name) for name in ('tests', 'failures', 'errors', 'skipped')}
    if counted['tests'] is None:
        for name in ('tests', 'failures', 'errors', 'skipped'):
            totals = [int(value) for value in re.findall(rf'\b{name}="(\d+)"', text)]
            counted[name] = sum(totals) if totals else None
    _ = head, root_match
    tests = counted['tests']
    return {
        'executed_n': tests,
        'passed_n': (tests - (counted['failures'] or 0) - (counted['errors'] or 0) - (counted['skipped'] or 0))
        if tests is not None else None,
        'failed_n': counted['failures'],
        'error_n': counted['errors'],
        'skipped_n': counted['skipped'],
        'source': rel_posix(path),
    }


def collect_snapshot(dirty_paths_ignored: set[str]) -> tuple[dict, dict]:
    """返回 (确定性快照, 易变来源)。工作树改动清单属于来源信息，不进 metrics.json。"""
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO_ROOT,
                          capture_output=True, text=True).stdout.strip()
    porcelain = subprocess.run(['git', '-c', 'core.quotepath=false', 'status', '--porcelain'],
                               cwd=REPO_ROOT, capture_output=True, text=True,
                               encoding='utf-8', errors='replace').stdout.splitlines()
    kept = []
    for line in porcelain:
        path = line[3:].strip()
        if ' -> ' in path:
            path = path.split(' -> ')[-1]
        normalized = path.strip('"').replace('\\', '/')
        if any(normalized.startswith(prefix) for prefix in dirty_paths_ignored):
            continue
        kept.append(normalized)
    provenance = {'git_dirty_files_n': len(kept),
                  'git_dirty_paths': sorted(kept),
                  'git_dirty_digest': 'sha256:' + sha256_bytes('\n'.join(sorted(kept)).encode())}
    return {'git_head': head}, provenance


# ---------------------------------------------------------------------------
# 旧数值扫描
# ---------------------------------------------------------------------------

def _bind_metric(line: str, metrics: dict) -> tuple[str | None, int | None]:
    """把文档里的数字绑定到本快照指标。带 required_keywords 的模式用于消歧（如“行”需同句提到后端）。"""
    normalized = line.replace(',', '')
    bindings = [
        (r'(\d+)\s*个?\s*Java\s*文件', 'java.main.file_n', ()),
        (r'(\d+)\s*张表', 'migrations.offline_distinct_table_n', ()),
        (rf'@Test\s*=\s*(\d+)', 'java.test.test_annotation_n', ()),
        (r'(\d+)\s*个?\s*接口', 'java.main.routes.actual_route_n', ()),
        (r'(\d+)\s*个?\s*(?:Controller|控制器)', 'java.main.controller_file_n', ()),
        (r'(\d+)\s*个?\s*(?:Service|服务类)', 'java.main.service_file_n', ()),
        (r'(\d+)\s*行', 'java.main.loc.total', ('后端', 'backend', 'Java', 'java')),
        (r'Python\s*(\d+)\s*个?\s*用例', 'tests.pytest.collected_n', ()),
        # 刻意不绑定 "N passed / N skipped"：那是命令级日志，不是项目级主张。
    ]
    for pattern, metric, keywords in bindings:
        if keywords and not any(keyword in line for keyword in keywords):
            continue
        found = re.search(pattern, normalized)
        if found:
            return metric, int(found.group(1))
    return None, None


def _metric_value(metrics: dict, dotted: str):
    node = metrics
    for part in dotted.split('.'):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def classify_line(line: str, metrics: dict) -> tuple[str, str | None]:
    bound_metric, bound_value = _bind_metric(line, metrics)
    # 明确标注为历史/旧稿的句子优先归为历史引用，不因数值不同就要求改写。
    if any(marker in line for marker in HISTORICAL_MARKERS):
        return 'historical_reference', bound_metric
    if bound_metric and bound_value is not None:
        actual = _metric_value(metrics, bound_metric)
        if bound_metric == 'migrations.offline_distinct_table_n' and \
                _metric_value(metrics, 'migrations.runtime_tables_n') is None:
            # 运行库未核验时，离线定义只能提供参考，不能宣判“必须改写”。
            return 'needs_review', bound_metric
        if isinstance(actual, int) and actual != bound_value:
            return 'needs_correction', bound_metric
        if isinstance(actual, int) and actual == bound_value:
            return 'current_claim', bound_metric
    if any(marker in line for marker in CURRENT_MARKERS):
        return 'current_claim', bound_metric
    return 'needs_review', bound_metric


def scan_claims(metrics: dict, exclude_prefixes: set[str] | None = None) -> list[dict]:
    root = REPO_ROOT / CLAIM_SCAN_ROOT
    excluded = exclude_prefixes if exclude_prefixes is not None else {rel_posix(EVIDENCE_DIR)}
    findings = []
    pattern = re.compile(r'(\d{2,5}(?:,\d{3})*)')
    candidates = []
    for directory in CLAIM_SCAN_DIRS:
        basis = REPO_ROOT / directory
        candidates += iter_files(basis, '*.md') + iter_files(basis, '*.html')
    if root.is_dir():
        candidates += sorted(p for p in root.glob('*.md') if p.is_file())
    for path in sorted(set(candidates)):
        relative = rel_posix(path)
        # 本流程自己生成的证据文件不是“待核对主张”，参与扫描会导致自指漂移。
        if any(relative.startswith(prefix) for prefix in excluded):
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not any(str(number) in line.replace(',', '') for number in CLAIM_NUMBERS):
                continue
            hits = [m.group(1) for m in pattern.finditer(line)
                    if int(m.group(1).replace(',', '')) in CLAIM_NUMBERS]
            if not hits:
                continue
            classification, metric = classify_line(line, metrics)
            findings.append({
                'file': rel_posix(path), 'line': lineno, 'numbers': hits,
                'classification': classification, 'bound_metric': metric,
                'context': line.strip()[:180],
            })
    return findings


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def build_metrics(*, collect: bool, junitxml: Path | None,
                  ignored_dirty_prefixes: set[str]) -> tuple[dict, list, dict, dict]:
    java_main = collect_java(JAVA_MAIN_ROOT, with_routes=True)
    java_test = collect_java(JAVA_TEST_ROOT, with_routes=False)
    vue = collect_vue()
    migrations = collect_migrations()
    pytest_metrics = collect_pytest(collect)
    if junitxml and junitxml.is_file():
        pytest_metrics.update(parse_junitxml(junitxml))
        pytest_metrics['reason'] = None
        pytest_metrics['junitxml_sha256'] = 'sha256:' + sha256_file(junitxml)
    elif junitxml:
        pytest_metrics['junit_reason'] = f'junitxml 不存在：{junitxml}'

    files = java_main.get('files', []) + java_test.get('files', []) + \
        vue.get('files', []) + migrations.get('files', [])
    digest_input = '\n'.join(f"{entry['path']}\t{entry['sha256']}" for entry in files)
    snapshot, provenance = collect_snapshot(ignored_dirty_prefixes)
    snapshot['source_count'] = len(files)
    snapshot['source_digest'] = 'sha256:' + sha256_bytes(digest_input.encode())

    metrics = {
        'schema_version': SCHEMA_VERSION,
        'task': 'FCT-P0-01',
        'snapshot': snapshot,
        'java': {
            'main': {k: v for k, v in java_main.items() if k != 'files'},
            'test': {k: v for k, v in java_test.items() if k != 'files'},
        },
        'vue': {k: v for k, v in vue.items() if k != 'files'},
        'migrations': {k: v for k, v in migrations.items() if k != 'files'},
        'tests': {'pytest': pytest_metrics},
        'environment': {
            'python': platform.python_version(),
            'pytest': _pytest_version(),
            'platform': platform.platform(),
        },
        'definitions': DEFINITIONS,
    }

    unavailable = []
    if java_main.get('reason'):
        unavailable.append({'metric': 'java.main', 'value': None, 'reason': java_main['reason']})
    if migrations.get('runtime_tables_n') is None:
        unavailable.append(runtime_db_reason())
    if pytest_metrics.get('executed_n') is None:
        unavailable.append({'metric': 'tests.pytest.executed_n', 'value': None,
                            'reason': '未提供 junitxml 或本轮仅收集；执行/通过/失败/跳过为 null，不记 0。'})

    sources = {'schema_version': SCHEMA_VERSION,
               'source_digest': snapshot['source_digest'],
               'files': {entry['path']: {'sha256': entry['sha256'], 'bytes': entry.get('bytes')}
                         for entry in files}}
    return metrics, unavailable, sources, provenance


def _pytest_version() -> str | None:
    try:
        import pytest
        return pytest.__version__
    except Exception:
        return None


def _self_check(metrics: dict, source_count: int) -> list[str]:
    problems = []
    for scope in ('main', 'test'):
        loc = metrics['java'][scope].get('loc')
        if not loc:
            continue
        if loc['code'] + loc['comment'] + loc['blank'] != loc['total']:
            problems.append(f'java.{scope}: code+comment+blank != total')
    loc = metrics['vue'].get('loc')
    if loc and loc['code'] + loc['comment'] + loc['blank'] != loc['total']:
        problems.append('vue: code+comment+blank != total')
    routes = metrics['java']['main'].get('routes')
    if routes and routes['actual_route_n'] > routes['route_annotation_n']:
        problems.append('routes: actual_route_n > route_annotation_n')
    if metrics['snapshot']['source_count'] != source_count:
        problems.append('snapshot.source_count 与来源列表不一致')
    return problems


def render_fact_sheet(metrics: dict, unavailable: list, problems: list) -> str:
    java_main = metrics['java']['main']
    java_test = metrics['java']['test']
    vue = metrics['vue']
    mig = metrics['migrations']
    pytest_m = metrics['tests']['pytest']
    snap = metrics['snapshot']
    routes = java_main.get('routes', {})

    def loc_row(name, node):
        if not node:
            return f'| {name} | null | null | null | null |'
        return (f"| {name} | {node['total']} | {node['blank']} | {node['comment']} | {node['code']} |")

    def value_or_null(value):
        return 'null' if value is None else value

    lines = [
        '# FCT-P0-01 事实表（自动生成）',
        '',
        '> 本文件由 `scripts/fact_ledger.py` 生成，请勿手工改数。每个数字的口径见文末“口径定义”。',
        '> `docs/competition/_fix_numbers.py` 是硬编码替换脚本，**不可作为事实来源**。',
        '',
        '## 1. 快照',
        '',
        '| 项 | 值 |',
        '|---|---|',
        f"| git HEAD | `{snap['git_head']}` |",
        f"| 纳入统计源文件数 | {snap['source_count']} |",
        f"| 统计源内容摘要 | `{snap['source_digest']}` |",
        '',
        '工作树改动清单（可能被其他进程实时改动）记录在 `run-meta.json`，不参与内容确定性比较。',
        '冻结校验：`python scripts/fact_ledger.py --verify-snapshot '
        f'{rel_posix(EVIDENCE_DIR)}/sources.json`。来源被改动/增删时退出码 2，不覆盖证据。',
        '',
        '## 2. 代码规模（Java / Vue）',
        '',
        '| 范围 | 总行 | 空行 | 注释行 | 代码行 |',
        '|---|---:|---:|---:|---:|',
        loc_row(f"Java main（{java_main.get('file_n')} 文件）", java_main.get('loc')),
        loc_row(f"Java test（{java_test.get('file_n')} 文件）", java_test.get('loc')),
        loc_row(f"Vue（{value_or_null(vue.get('file_n'))} 文件）", vue.get('loc')),
        '',
        f"- Java main 中 Controller 文件 {java_main.get('controller_file_n')} 个、"
        f"文件名以 Service 结尾 {java_main.get('service_file_n')} 个（按文件命名统计，不是接口数）。",
        '',
        '## 3. 路由：注解数与实际路由数（口径分开）',
        '',
        '| 指标 | 值 | 说明 |',
        '|---|---:|---|',
        f"| 路由注解数（含类级） | {routes.get('route_annotation_n')} | 注解出现次数，不等于接口数 |",
        f"| 实际路由数（方法+路径去重） | {routes.get('actual_route_n')} | 类级基路径已拼接 |",
        f"| 无法静态解析的路径注解 | {routes.get('unresolved_annotation_n')} | 常量拼接等，未静默丢弃 |",
        '',
        '## 4. 数据库表',
        '',
        '| 指标 | 值 | 说明 |',
        '|---|---:|---|',
        f"| migration 文件数 | {mig.get('file_n')} | 仅 `src/main/resources/db/migration` |",
        f"| migration 中 CREATE TABLE 数 | {mig.get('create_table_n')} | 含 IF NOT EXISTS |",
        f"| 离线定义表名去重数 | {value_or_null(mig.get('offline_distinct_table_n'))} | 仅离线定义口径 |",
        f"| 运行库实际表数 | {value_or_null(mig.get('runtime_tables_n'))} | 未连接数据库，见“缺失统计源” |",
        '',
        '## 5. 测试：收集 / 执行 分开',
        '',
        '| 指标 | 值 |',
        '|---|---:|',
        f"| pytest 收集数 | {value_or_null(pytest_m.get('collected_n'))} |",
        f"| 执行数 | {value_or_null(pytest_m.get('executed_n'))} |",
        f"| 通过 | {value_or_null(pytest_m.get('passed_n'))} |",
        f"| 失败 | {value_or_null(pytest_m.get('failed_n'))} |",
        f"| 错误 | {value_or_null(pytest_m.get('error_n'))} |",
        f"| 跳过 | {value_or_null(pytest_m.get('skipped_n'))} |",
        f"| Java @Test 注解数 | {value_or_null(java_test.get('test_annotation_n'))} |",
        '',
        '注解数不等于执行数；未提供 junitxml 时执行类指标为 null。',
        '',
        '## 6. 缺失统计源（值为 null，不记 0）',
        '',
    ]
    if unavailable:
        lines += ['| 指标 | 原因 |', '|---|---|']
        lines += [f"| `{item['metric']}` | {item['reason']} |" for item in unavailable]
    else:
        lines.append('无。')
    lines += ['', '## 7. 自检', '']
    lines += ['- 恒等式与路由计数自检通过。'] if not problems else [f'- **自检失败**：{p}' for p in problems]
    lines += ['', '## 8. 口径定义', '', '| 指标 | 定义 |', '|---|---|']
    lines += [f"| `{key}` | {value} |" for key, value in metrics['definitions'].items()]
    lines += ['', '## 9. 实际路由明细（节选）', '',
              '| HTTP | 路径 | 控制器 |', '|---|---|---|']
    for route in routes.get('routes', [])[:60]:
        lines.append(f"| {route['http']} | `{route['path']}` | {route['controller']} |")
    if len(routes.get('routes', [])) > 60:
        lines.append(f'\n> 其余 {len(routes["routes"]) - 60} 条见 `metrics.json` → `java.main.routes.routes`。')
    return '\n'.join(lines) + '\n'


def render_claims(findings: list[dict]) -> str:
    buckets = {'needs_correction': [], 'needs_review': [], 'historical_reference': [],
               'current_claim': []}
    for item in findings:
        buckets[item['classification']].append(item)
    lines = [
        '# FCT-P0-01 过期主张清单（自动生成，只检测不改文）',
        '',
        '> 扫描范围：`docs/competition/**`、`docs/audit/**`、`docs/*.md`（对外材料）；`docs/development/**` 是工作报告，不参与核对。',
        '> 只做扫描与分类，**不修改任何文档**。分类规则：能绑定到本快照指标且数值不同 → `needs_correction`；',
        '> 命中历史措辞 → `historical_reference`；命中当前措辞 → `current_claim`；其余 → `needs_review`。',
        '> “N 张表”绑定的是**离线 migration 定义去重数**，不是运行库表数（后者为 null，未核验）；',
        '> “N 个接口”绑定的是静态解析出的 (HTTP方法, 路径) 去重数，常量拼接路径未计入并在 `unresolved_annotation_n` 单列。',
        '',
        '| 分类 | 条数 | 含义 |',
        '|---|---:|---|',
        f"| needs_correction | {len(buckets['needs_correction'])} | 与本次冻结指标冲突，必须人工改写 |",
        f"| needs_review | {len(buckets['needs_review'])} | 无法自动判定，需按上下文人工确认 |",
        f"| historical_reference | {len(buckets['historical_reference'])} | 明确写为历史/旧稿，可保留 |",
        f"| current_claim | {len(buckets['current_claim'])} | 与本次指标一致，视为当前主张 |",
        '',
    ]
    for name in ('needs_correction', 'needs_review', 'historical_reference', 'current_claim'):
        items = buckets[name]
        lines += [f'## {name}（{len(items)}）', '']
        if not items:
            lines += ['无。', '']
            continue
        lines += ['| 文件:行 | 命中数字 | 绑定指标 | 原文（截断） |', '|---|---|---|---|']
        for item in items[:80]:
            context = item['context'].replace('|', '\\|')
            lines.append(f"| {item['file']}:{item['line']} | {', '.join(item['numbers'])} | "
                         f"{item['bound_metric'] or '-'} | {context} |")
        if len(items) > 80:
            lines.append(f'\n> 其余 {len(items) - 80} 条省略，完整列表可用 `--claims-json` 另存。')
        lines.append('')
    return '\n'.join(lines) + '\n'


def verify_snapshot(lock_path: Path, sources: dict) -> list[str]:
    """对照已记录的来源清单，列出新增/缺失/变更的文件。返回差异描述列表。"""
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    recorded = lock.get('files', {})
    current = sources.get('files', {})
    problems = []
    changed = sorted(path for path in recorded.keys() & current.keys()
                     if recorded[path]['sha256'] != current[path]['sha256'])
    added = sorted(current.keys() - recorded.keys())
    removed = sorted(recorded.keys() - current.keys())
    for label, items in (('changed', changed), ('added', added), ('removed', removed)):
        if items:
            problems.append(f'{label}: {len(items)} 个，例 {items[:5]}')
    return problems


def write_outputs(metrics: dict, unavailable: list, sources: dict, findings: list,
                  problems: list, output_dir: Path, provenance: dict, args) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True)
    (output_dir / 'metrics.json').write_text(payload + '\n', encoding='utf-8')
    (output_dir / 'sources.json').write_text(
        json.dumps(sources, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (output_dir / 'fact-sheet.md').write_text(
        render_fact_sheet(metrics, unavailable, problems), encoding='utf-8')
    (output_dir / 'stale-claims.md').write_text(render_claims(findings), encoding='utf-8')
    meta = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'command': ' '.join(sys.argv),
        'output_dir': rel_posix(output_dir),
        'metrics_digest': 'sha256:' + sha256_bytes(payload.encode()),
        'junitxml': rel_posix(args.junitxml) if args.junitxml else None,
        'collect_only_mode': not args.collect_pytest,
        **provenance,
    }
    (output_dir / 'run-meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=EVIDENCE_DIR)
    parser.add_argument('--junitxml', type=Path, default=None)
    parser.add_argument('--collect-pytest', action='store_true',
                        help='运行 pytest --collect-only 获取收集数（约 35 秒）')
    parser.add_argument('--claims-json', type=Path, default=None)
    parser.add_argument('--verify-snapshot', type=Path, default=None,
                        help='对照已生成的 sources.json 校验快照是否仍冻结；不一致时退出码 2')
    args = parser.parse_args()

    # 证据目录与 .runtime/ 是本流程的产物，不能影响“同一快照”的判定。
    ignored = {rel_posix(EVIDENCE_DIR), rel_posix(args.output_dir), '.runtime/'}
    metrics, unavailable, sources, provenance = build_metrics(
        collect=args.collect_pytest, junitxml=args.junitxml, ignored_dirty_prefixes=ignored)
    problems = _self_check(metrics, len(sources['files']))
    drift = verify_snapshot(args.verify_snapshot, sources) if args.verify_snapshot else []
    if drift:
        print('snapshot=DRIFTED')
        for item in drift:
            print(f'  drift: {item}')
        print('检测到快照变动：不覆盖已有证据，退出码 2。')
        return 2
    findings = scan_claims(metrics, exclude_prefixes={'docs/development/fct-p0-01-evidence', '.runtime/'})
    write_outputs(metrics, unavailable, sources, findings, problems, args.output_dir,
                  provenance, args)
    if args.claims_json:
        args.claims_json.parent.mkdir(parents=True, exist_ok=True)
        args.claims_json.write_text(
            json.dumps(findings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f"metrics_digest={metrics['snapshot']['source_digest']}")
    print(f"java_main_files={metrics['java']['main'].get('file_n')} "
          f"routes={metrics['java']['main'].get('routes', {}).get('actual_route_n')}")
    print(f"vue_files={metrics['vue'].get('file_n')} create_table={metrics['migrations'].get('create_table_n')}")
    print(f"pytest_collected={metrics['tests']['pytest'].get('collected_n')} "
          f"needs_correction={sum(1 for f in findings if f['classification'] == 'needs_correction')}")
    print(f"self_check={'PASS' if not problems else 'FAIL: ' + '; '.join(problems)}")
    print(f"snapshot={'FROZEN' if args.verify_snapshot else 'NOT_VERIFIED'}")
    print(f"output_dir={rel_posix(args.output_dir)}")
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
