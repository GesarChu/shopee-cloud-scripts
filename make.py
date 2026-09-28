# -*- coding: utf-8 -*-
"""make.py — 讀商品規格檔，寫出一支片 5 鏡的首幀指令／影片提示詞／口白腳本（共 15 個檔）。

用法：
  python make.py spec/<商品>.json --out out/<包名>
  python make.py spec/<商品>.json                  # 沒給 --out ⇒ 寫到 out/<規格檔的 package>

規格檔欄位說明：spec/README.md。寫完建議接著跑：
  python tools/script-lint.py out/<包名>/口白腳本_*D.txt
"""
import argparse
import os
import sys

import genlib

ROOT = os.path.dirname(os.path.abspath(__file__))


def _inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder + os.sep)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="商品規格檔 → 5 鏡的 Qwen 首幀指令＋H3 影片提示詞＋口白腳本")
    ap.add_argument("spec", help="規格檔，例如 spec/TTL花雕雞麵.json")
    ap.add_argument("--out", help="輸出資料夾（預設 out/<規格檔的 package>）")
    args = ap.parse_args(argv)

    try:
        spec = genlib.load_spec(args.spec)
    except (OSError, genlib.SpecError) as e:
        print("❌ %s" % e, file=sys.stderr)
        return 2
    out_dir = args.out or os.path.join("out", spec["package"])
    if _inside(out_dir, os.path.join(ROOT, "golden")):
        print("❌ 不准寫進 golden/（那是驗收標準）：%s" % out_dir, file=sys.stderr)
        return 2

    written = genlib.write_package(spec, out_dir)
    for sid, shot in zip(genlib.shot_ids(spec), spec["shots"]):
        print(spec["package"], sid, "｜".join(shot["line"]))
    print("✅ 寫出 %d 個檔 → %s" % (len(written), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
