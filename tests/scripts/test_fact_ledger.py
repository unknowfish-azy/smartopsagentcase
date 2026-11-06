import json

import pytest

from scripts import fact_ledger as ledger


# ---------------------------------------------------------------------------
# 行分类：空行 / 注释 / 代码
# ---------------------------------------------------------------------------

def test_count_lines_separates_blank_comment_and_code():
    text = 'package a;\n' \
           '\n' \
           '// 行注释\n' \
           '/* 块注释\n' \
           '   继续\n' \
           '   结束 */\n' \
           'public class A {   // 尾随注释\n' \
           '    String s = "http://example.com";\n' \
           '}\n'
    counted = ledger.count_lines(text)
    assert counted['total'] == 9
    assert counted['blank'] == 1
    assert counted['comment'] == 4
    assert counted['code'] == 4
    assert counted['code'] + counted['comment'] + counted['blank'] == counted['total']


def test_count_lines_does_not_treat_string_slashes_as_comment():
    counted = ledger.count_lines('var u = "a//b";\n')
    assert counted['code'] == 1
    assert counted['comment'] == 0


def test_count_lines_handles_html_comments_only_when_enabled():
    text = '<!-- 注释 -->\n<div>ok</div>\n'
    with_html = ledger.count_lines(text, html_comments=True)
    without_html = ledger.count_lines(text)
    assert with_html['comment'] == 1
    assert without_html['comment'] == 0
    assert with_html['code'] == 1
    assert without_html['code'] == 2


# ---------------------------------------------------------------------------
# 路由解析
# ---------------------------------------------------------------------------

def test_route_parsing_composes_class_base_and_method_paths():
    text = '''
@RestController
@RequestMapping("/api/demo")
public class DemoController {
    @GetMapping("/a")
    public String a() { return ""; }

    @PostMapping(value = "/b", produces = "application/json")
    public String b() { return ""; }

    @RequestParam String ignored(@RequestParam("x") String x) { return x; }

    @RequestMapping(value = "/c", method = RequestMethod.PUT)
    public String c() { return ""; }
}
'''
    scanned = ledger.scan_java_routes(text)
    pairs = {(item['http'], item['path']) for item in scanned['routes']}
    assert ('GET', '/api/demo/a') in pairs
    assert ('POST', '/api/demo/b') in pairs
    assert ('PUT', '/api/demo/c') in pairs
    assert scanned['route_annotation_n'] == 4
    assert scanned['actual_route_n'] == 3
    assert scanned['unresolved_annotation_n'] == 0


def test_route_parsing_expands_array_of_paths_and_bare_annotation():
    text = '''
@RestController
@RequestMapping("/api/x")
public class X {
    @GetMapping({"/a", "/b"})
    public void many() {}

    @GetMapping
    public void root() {}
}
'''
    scanned = ledger.scan_java_routes(text)
    pairs = {(item['http'], item['path']) for item in scanned['routes']}
    assert pairs == {('GET', '/api/x/a'), ('GET', '/api/x/b'), ('GET', '/api/x')}
    assert scanned['actual_route_n'] == 3


def test_route_parsing_marks_constant_path_as_unresolved_instead_of_dropping():
    text = '''
@RestController
@RequestMapping(ApiPaths.BASE)
public class Y {
    @GetMapping(ApiPaths.DETAIL)
    public void detail() {}
}
'''
    scanned = ledger.scan_java_routes(text)
    assert scanned['unresolved_annotation_n'] == 1
    assert scanned['actual_route_n'] == 1
    assert scanned['routes'][0]['path'] == '*UNRESOLVED*'


# ---------------------------------------------------------------------------
# 旧数值绑定与分类
# ---------------------------------------------------------------------------

METRICS = {
    'java': {'main': {'file_n': 271,
                      'loc': {'total': 27518},
                      'controller_file_n': 52,
                      'service_file_n': 65,
                      'routes': {'actual_route_n': 376}},
             'test': {'test_annotation_n': 532}},
    'migrations': {'offline_distinct_table_n': 100},
    'tests': {'pytest': {'collected_n': 566, 'passed_n': 540, 'skipped_n': 24}},
}


def test_binding_marks_conflicting_table_count_as_needs_review_when_db_unknown():
    line = 'MySQL 8，**80 张表**，迁移脚本幂等'
    classification, metric = ledger.classify_line(line, METRICS)
    assert classification == 'needs_review'
    assert metric == 'migrations.offline_distinct_table_n'


def test_table_claim_is_correctable_once_runtime_tables_verified():
    metrics = json.loads(json.dumps(METRICS))
    metrics['migrations']['runtime_tables_n'] = 100
    classification, _ = ledger.classify_line('MySQL 8，**80 张表**，迁移脚本幂等', metrics)
    assert classification == 'needs_correction'


def test_binding_agrees_with_snapshot_as_current_claim():
    line = '后端 271 个 Java 文件'
    classification, metric = ledger.classify_line(line, METRICS)
    assert classification == 'current_claim'
    assert metric == 'java.main.file_n'


def test_command_level_passed_count_is_not_treated_as_project_claim():
    line = '| Agent pytest | `pytest tests/agent -v --tb=no` | — | 80 passed | NOT_RUN |'
    classification, metric = ledger.classify_line(line, METRICS)
    assert metric is None
    assert classification in {'needs_review', 'historical_reference'}


def test_thousands_separator_is_normalized_before_binding():
    line = '后端 219 Java 文件 / 17,981 行 / 45 Controller'
    classification, metric = ledger.classify_line(line, METRICS)
    assert classification == 'needs_correction'
    # 先命中 Java 文件数绑定
    assert metric == 'java.main.file_n'


def test_line_without_binding_falls_back_to_context_markers():
    assert ledger.classify_line('旧稿曾写 219 个 Java 文件', METRICS)[0] == 'historical_reference'
    assert ledger.classify_line('当前是 271 个 Java 文件', METRICS)[0] == 'current_claim'
    assert ledger.classify_line('这里出现 219 个 Java 文件', METRICS)[0] == 'needs_correction'
    assert ledger.classify_line('这里出现一些数字 219', METRICS)[0] == 'needs_review'


def test_unavailable_metric_is_not_reported_as_zero():
    metrics, unavailable, _, _ = ledger.build_metrics(
        collect=False, junitxml=None,
        ignored_dirty_prefixes={'docs/development/fct-p0-01-evidence', '.runtime/'})
    pytest_metrics = metrics['tests']['pytest']
    assert pytest_metrics['collected_n'] is None
    assert pytest_metrics['executed_n'] is None
    assert pytest_metrics['passed_n'] is None
    assert metrics['migrations']['runtime_tables_n'] is None
    reasons = {item['metric']: item['value'] for item in unavailable}
    assert reasons['tests.pytest.executed_n'] is None
    assert reasons['migrations.runtime_tables_n'] is None


def test_metrics_content_has_no_timestamp():
    metrics, _, _, _ = ledger.build_metrics(
        collect=False, junitxml=None,
        ignored_dirty_prefixes={'docs/development/fct-p0-01-evidence', '.runtime/'})
    payload = json.dumps(metrics)
    assert 'generated_at' not in payload
    # 工作树改动清单是易变来源信息，必须留在 run-meta.json，不能进 metrics
    assert 'git_dirty' not in payload


def test_same_snapshot_produces_identical_metrics():
    first, _, _, _ = ledger.build_metrics(
        collect=False, junitxml=None,
        ignored_dirty_prefixes={'docs/development/fct-p0-01-evidence', '.runtime/'})
    second, _, _, _ = ledger.build_metrics(
        collect=False, junitxml=None,
        ignored_dirty_prefixes={'docs/development/fct-p0-01-evidence', '.runtime/'})
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first['snapshot']['source_digest'] == second['snapshot']['source_digest']


def test_missing_source_yields_null_and_reason():
    scope = ledger.collect_java('backend/src/main/java-not-exist', with_routes=True)
    assert scope['file_n'] is None
    assert '统计源缺失' in scope['reason']


def test_self_check_catches_broken_identity():
    metrics, _, _, _ = ledger.build_metrics(
        collect=False, junitxml=None,
        ignored_dirty_prefixes={'docs/development/fct-p0-01-evidence', '.runtime/'})
    assert ledger._self_check(metrics, metrics['snapshot']['source_count']) == []
    metrics['vue']['loc']['code'] += 1
    problems = ledger._self_check(metrics, metrics['snapshot']['source_count'])
    assert any('vue' in problem for problem in problems)


def test_verify_snapshot_lists_changed_added_and_removed(tmp_path):
    lock = tmp_path / 'sources.json'
    lock.write_text(json.dumps({'files': {'a.java': {'sha256': 'aa'},
                                          'b.java': {'sha256': 'bb'}}}), encoding='utf-8')
    current = {'files': {'a.java': {'sha256': 'zz'}, 'c.java': {'sha256': 'cc'}}}
    problems = ledger.verify_snapshot(lock, current)
    joined = ' '.join(problems)
    assert 'changed' in joined and 'added' in joined and 'removed' in joined

    same = {'files': {'a.java': {'sha256': 'aa'}, 'b.java': {'sha256': 'bb'}}}
    assert ledger.verify_snapshot(lock, same) == []


def _run_main(monkeypatch, argv, metrics):
    written = []
    monkeypatch.setattr(ledger, 'build_metrics',
                        lambda **kwargs: (metrics, [], {'files': {}}, {}))
    monkeypatch.setattr(ledger, 'verify_snapshot', lambda path, sources: [])
    monkeypatch.setattr(ledger, 'scan_claims', lambda *a, **k: [])
    monkeypatch.setattr(ledger, '_self_check', lambda m, n: [])
    monkeypatch.setattr(ledger, 'write_outputs', lambda *a, **k: written.append(1))
    monkeypatch.setattr(ledger.sys, 'argv', ['fact_ledger.py'] + argv)
    return ledger.main(), written


_MINIMAL_METRICS = {
    'snapshot': {'source_digest': 'sha256:x'},
    'java': {'main': {'file_n': 1, 'routes': {'actual_route_n': 1}}},
    'vue': {'file_n': 1},
    'migrations': {'create_table_n': 1},
    'tests': {'pytest': {'collected_n': None}},
}


def test_verify_mode_is_read_only_and_never_writes_evidence(monkeypatch, tmp_path):
    # 校验模式只读：曾经在 FROZEN 分支写回证据目录，导致已钉住的快照被覆盖。
    code, written = _run_main(
        monkeypatch, ['--verify-snapshot', str(tmp_path / 'lock.json'),
                      '--output-dir', str(tmp_path)], _MINIMAL_METRICS)
    assert code == 0
    assert written == []


def test_collect_mode_still_writes_evidence(monkeypatch, tmp_path):
    code, written = _run_main(
        monkeypatch, ['--output-dir', str(tmp_path)], _MINIMAL_METRICS)
    assert code == 0
    assert written == [1]


def test_claims_scan_is_read_only(tmp_path):
    target = ledger.REPO_ROOT / 'docs/competition/defense.md'
    before = target.read_bytes()
    metrics, _, _, _ = ledger.build_metrics(
        collect=False, junitxml=None,
        ignored_dirty_prefixes={'docs/development/fct-p0-01-evidence', '.runtime/'})
    ledger.scan_claims(metrics)
    assert target.read_bytes() == before
    rendered = ledger.render_claims([
        {'file': 'docs/x.md', 'line': 1, 'numbers': ['80'],
         'classification': 'needs_correction', 'bound_metric': 'migrations.offline_distinct_table_n',
         'context': 'a|b'}
    ])
    assert 'needs_correction' in rendered
    assert 'a\\|b' in rendered
