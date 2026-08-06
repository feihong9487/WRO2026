#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧香爐 — 測試執行器（不依賴 pytest）
=============================================================
為什麼不直接用 pytest：
  本機系統 Python 受 PEP 668 保護，pip 裝不了套件，而
  `--break-system-packages` 會動到系統環境，風險不值得。
  這些測試只用到 assert 與模組層級的匯入，本檔即可完整執行。

  若環境有 pytest，用它跑結果等價（本檔的測試檔完全相容）。

行為：
  * 遞迴尋找 test_*.py，逐一執行其中的 test_* 函式
  * 全過 exit 0；任一失敗 exit 1 —— 給 hooks 與 auto_loop.sh 判定用
  * 輸出格式盡量貼近 pytest，方便對照

用法：
  python3 run_tests.py                # 全部
  python3 run_tests.py -k PLA         # 只跑名稱含 PLA 的
  python3 run_tests.py -v             # 顯示每條通過的規則名稱
  python3 run_tests.py CAD自檢        # 限定目錄
"""

import argparse
import contextlib
import importlib.util
import io
import sys
import traceback
from pathlib import Path

# ★不要寫／不要用 .pyc★ 2026-08-07 踩到：sed 把 `= 2` 改成 `= 1`，
#   字元數相同、mtime 又落在同一秒，Python 的快取檢查（size + mtime）判定沒變，
#   於是測試讀到的是舊值——負向測試「通過」了，其實驗的是改之前的參數。
#   測試執行器讀到過期的參數，比測試失敗更危險。
sys.dont_write_bytecode = True

ROOT = Path(__file__).parent
SKIP_DIRS = {".git", "__pycache__", ".claude", "node_modules"}


def find_test_files(targets):
    files = []
    for t in targets:
        p = Path(t)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_file() and p.name.startswith("test_"):
            files.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("test_*.py")):
                if not any(part in SKIP_DIRS for part in f.parts):
                    files.append(f)
    return sorted(set(files))


def load_module(path):
    importlib.invalidate_caches()
    """
    以檔案所在目錄為匯入根載入模組。

    這模仿 pytest 的 rootdir 行為：測試檔旁邊的 mech_params.py
    要能用 `import mech_params` 匯入。
    """
    d = str(path.parent)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description="智慧香爐測試執行器（免 pytest）")
    ap.add_argument("targets", nargs="*", default=["."],
                    help="要掃描的檔案或目錄（預設：專案全部）")
    ap.add_argument("-k", dest="filter", default=None,
                    help="只跑名稱含此字串的測試")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="列出每條通過的規則")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="只輸出摘要與失敗項（與 pytest -q 相近）")
    ap.add_argument("--scope", choices=["all", "core", "later"], default="all",
                    help="all=全部（預設）｜core=當前里程碑 P0/P1｜later=P3 機構。"
                         "範圍定義在 CAD自檢/mech_params.py，不是略過測試，"
                         "而是換個視角看同一組規則")
    args = ap.parse_args()

    # 讀取里程碑範圍定義
    scope_set = None
    if args.scope != "all":
        try:
            sys.path.insert(0, str(ROOT / "CAD自檢"))
            import mech_params as _P
            scope_set = _P.SCOPE_CORE if args.scope == "core" else _P.SCOPE_LATER
            print(f"【範圍：{args.scope}】里程碑 {_P.MILESTONE}"
                  f"（{len(scope_set)} 條規則；其餘不在本次範圍，非略過）")
        except Exception as e:
            print(f"讀不到範圍定義，改跑全部：{e}")

    files = find_test_files(args.targets or ["."])
    if not files:
        print("找不到任何 test_*.py")
        return 1

    total = passed = 0
    failures = []
    captured_notes = []

    for f in files:
        rel = f.relative_to(ROOT) if ROOT in f.parents or f.parent == ROOT else f
        try:
            mod = load_module(f)
        except Exception as e:
            failures.append((str(rel), "<模組匯入>", f"{type(e).__name__}: {e}"))
            total += 1
            print(f"E {rel} — 匯入失敗：{type(e).__name__}: {e}")
            continue

        tests = [(n, fn) for n, fn in vars(mod).items()
                 if n.startswith("test_") and callable(fn)]
        tests.sort(key=lambda x: x[0])

        if not args.quiet and tests:
            print(f"\n{rel}")

        for name, fn in tests:
            if args.filter and args.filter not in name:
                continue
            if scope_set is not None and name not in scope_set:
                continue
            total += 1
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    fn()
                passed += 1
                out = buf.getvalue().strip()
                if out:
                    captured_notes.append(out)
                if args.verbose:
                    print(f"  ✓ {name}")
                elif not args.quiet:
                    print(".", end="", flush=True)
            except AssertionError as e:
                msg = str(e).strip()
                if not msg:
                    tb = traceback.extract_tb(sys.exc_info()[2])[-1]
                    msg = f"斷言失敗（{f.name}:{tb.lineno}）：{(tb.line or '').strip()}"
                failures.append((str(rel), name, msg))
                if not args.quiet:
                    print("F", end="", flush=True)
            except Exception as e:
                failures.append((str(rel), name,
                                 f"{type(e).__name__}: {e}"))
                if not args.quiet:
                    print("E", end="", flush=True)

        if not args.quiet and tests and not args.verbose:
            print()

    # 測試裡 print 出來的說明（例如待實測清單）
    for note in captured_notes:
        print(note)

    if failures:
        print("\n" + "=" * 62)
        print(f"失敗 {len(failures)} 項")
        print("=" * 62)
        for path, name, msg in failures:
            print(f"\n✗ {path}::{name}")
            for line in msg.splitlines():
                print(f"    {line}")

    print("\n" + "-" * 62)
    print(f"{passed} passed, {len(failures)} failed（共 {total} 條規則、{len(files)} 個檔案）")
    if failures:
        print("依 CLAUDE.md §5.2：修正設計參數，不得修改測試斷言或放寬安全下限。")
        print("衝突無解時依 §9 格式回報卡關。")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
