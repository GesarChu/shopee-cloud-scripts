# -*- coding: utf-8 -*-
"""工單 #1 驗收測試：make.py 產出要跟 golden/ 逐位元組相同。

  python test_golden.py      # 不用裝 pytest
  pytest test_golden.py      # 有 pytest 也可以

驗收標準（README 工單 #1）：
  1. 兩份規格檔產出的 30 個檔跟 golden/ 逐位元組相同（多檔、少檔也算失敗）
  2. genlib.py、make.py 沒有 exec／eval、沒有寫死的絕對路徑
  4. tools/script-lint.py 能跑產出的口白腳本
另外順便守：影片提示詞不寫左右手、make.py 不准寫進 golden/、規格檔寫錯會講清楚。
"""
import ast
import glob
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import genlib  # noqa: E402

SPECS = ["spec/TTL花雕雞麵.json", "spec/歐萊德咖啡因洗髮精.json"]
GOLDEN = os.path.join(ROOT, "golden")


def _files(folder):
    return sorted(os.path.relpath(p, folder).replace(os.sep, "/")
                  for p in glob.glob(os.path.join(folder, "**", "*"), recursive=True) if os.path.isfile(p))


def _make(spec, out_dir):
    return subprocess.run([sys.executable, os.path.join(ROOT, "make.py"), spec, "--out", out_dir], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")


def _load(spec):
    return genlib.load_spec(os.path.join(ROOT, spec))


# ── 1. 逐位元組相同 ───────────────────────────────────────────────────────────
def test_golden_byte_identical():
    same, problems = 0, []
    with tempfile.TemporaryDirectory() as tmp:
        for spec in SPECS:
            package = _load(spec)["package"]
            out_dir = os.path.join(tmp, package)
            r = _make(spec, out_dir)
            assert r.returncode == 0, "make.py %s 失敗：\n%s%s" % (spec, r.stdout, r.stderr)
            golden_dir = os.path.join(GOLDEN, package)
            want, got = _files(golden_dir), _files(out_dir)
            problems += ["%s：少了 %s" % (package, f) for f in sorted(set(want) - set(got))]
            problems += ["%s：多了 %s" % (package, f) for f in sorted(set(got) - set(want))]
            for rel in sorted(set(want) & set(got)):
                with open(os.path.join(golden_dir, rel), "rb") as a, open(os.path.join(out_dir, rel), "rb") as b:
                    ga, gb = a.read(), b.read()
                if ga == gb:
                    same += 1
                    continue
                i = next((k for k in range(min(len(ga), len(gb))) if ga[k] != gb[k]), min(len(ga), len(gb)))
                problems.append("%s/%s：第 %d 位元組起不同\n    golden：%r\n    產出  ：%r"
                                % (package, rel, i, ga[max(0, i - 30):i + 50], gb[max(0, i - 30):i + 50]))
    print("  golden 逐位元組相同：%d/30" % same)
    assert not problems and same == 30, "\n".join(problems)


# ── 2. 沒有 exec、沒有寫死的本機路徑 ──────────────────────────────────────────
# 絕對路徑：C:/…、E:\…、/c/tmp/…、/home/…、\\server\…、~/…（單獨一個 "/" 是 split 用的分隔符，不算）
_ABS_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/[^\s/]+/|\\\\|~[\\/])")


def test_no_exec_no_local_paths():
    problems = []
    for name in ("genlib.py", "make.py"):
        tree = ast.parse(open(os.path.join(ROOT, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval", "compile", "__import__"):
                problems.append("%s:%d 呼叫了 %s()" % (name, node.lineno, node.func.id))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                    _ABS_PATH.match(node.value) or re.search(r"[A-Za-z]:[\\/]", node.value)):
                problems.append("%s:%d 寫死路徑 %r" % (name, node.lineno, node.value[:60]))
    assert not problems, "\n".join(problems)


# ── 4. script-lint 能跑 ──────────────────────────────────────────────────────
def test_script_lint_runs_on_output():
    with tempfile.TemporaryDirectory() as tmp:
        for spec in SPECS:
            out_dir = os.path.join(tmp, _load(spec)["package"])
            assert _make(spec, out_dir).returncode == 0
            files = sorted(glob.glob(os.path.join(out_dir, "口白腳本_*D.txt")))
            assert len(files) == 5
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "script-lint.py")] + files, cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8")
            # exit 0＝沒硬傷、1＝有 🔴（lint 的正常結果）；其他（例如 Traceback）＝跑不動
            assert r.returncode in (0, 1) and "Traceback" not in r.stderr, r.stdout + r.stderr
            assert "口白腳本檢查：5 個檔" in r.stdout, r.stdout
            print("  script-lint %s：exit %d（%s）" % (os.path.basename(out_dir), r.returncode, r.stdout.strip().splitlines()[-1]))


# ── 規則守門 ─────────────────────────────────────────────────────────────────
def test_video_prompts_never_say_left_or_right():
    for spec in SPECS:
        for rel, text in genlib.render_package(_load(spec)).items():
            if rel.startswith("prompt_"):
                hit = re.search(r"\b(left|right)\b", text)
                assert not hit, "%s %s 寫了左右手：…%s…" % (spec, rel, text[max(0, hit.start() - 40):hit.end() + 20])


def test_expressions_avoid_banned_words():
    for key, texts in genlib.EXPRESSION.items():
        for w in genlib.BANNED_EXPRESSION_WORDS:
            assert all(w not in t for t in texts), "表情 %s 寫了 %s，會翻眼（CLAUDE #99）" % (key, w)


def test_make_refuses_to_write_into_golden():
    target = os.path.join("golden", "不該出現的資料夾")
    r = _make(SPECS[0], target)
    assert r.returncode == 2 and not os.path.exists(os.path.join(ROOT, target)), r.stdout + r.stderr


def test_spec_errors_are_explained():
    base = _load(SPECS[0])
    cases = [
        (lambda s: s["shots"].pop(), "5 鏡"),
        (lambda s: s["product"].update(colour="red"), "不認得的欄位"),
        (lambda s: s["person"].pop("qwen"), "缺欄位 qwen"),
        (lambda s: s["shots"][4].update(line=["常加班的", "連結我放下面"]), "連結"),
        (lambda s: s["shots"][0].update(line=["只有一句"]), "兩個半句"),
        (lambda s: s.update(package="../golden/x"), "不能帶路徑"),
    ]
    for mutate, expect in cases:
        spec = {**base, "person": dict(base["person"]), "product": dict(base["product"]), "shots": [dict(x) for x in base["shots"]]}
        mutate(spec)
        try:
            genlib.validate_spec(spec)
        except genlib.SpecError as e:
            assert expect in str(e), "錯誤訊息沒講到「%s」：%s" % (expect, e)
        else:
            raise AssertionError("應該擋下：%s" % expect)


def test_braces_in_spec_text_are_safe():
    spec = _load(SPECS[0])
    spec["product"] = dict(spec["product"], look_video="bag with {side} {0} printed on it")
    text = genlib.render_package(spec)["prompt_tt2D.txt"]
    assert "bag with {side} {0} printed on it upright in one hand" in text


# ── 不裝 pytest 也能跑 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", name, "\n ", str(e).replace("\n", "\n  ") or type(e).__name__)
    print("\n%d/%d 通過" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
