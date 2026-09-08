"""Va loi cat URL cua browser_tool tren Windows (Hermes).

VAN DE
------
Tren Windows, `_find_agent_browser()` tra ve mot npm bin shim:

    <hermes-agent>\\node_modules\\.bin\\agent-browser.CMD

Ruot shim do la:

    "%_prog%" "%dp0%\\..\\agent-browser\\bin\\agent-browser.js" %*

`%*` bung lai tham so KHONG nhay, va cmd.exe coi '&' la dau tach lenh -> moi URL
co query param bi cat cut am tham.

Bang chung do duoc (26/08/2026):
    gui di : ...ads/library/?active_status=active&ad_type=all&country=VN&q=HAPAS
    that su: ...ads/library/?active_status=active
    stderr : 'ad_type' is not recognized as an internal or external command

Hau qua: tool `fb_ads_library` LUON mo trang Ad Library trong, nen bao "0 ad" cho
moi thuong hieu -> agent dua ra ket luan thi truong SAI ma trong rat dang tin.

Da thu va DEU THAT BAI (dung thu lai):
  - Bo nhay qua list2cmdline (chen khoang trang): co bo nhay that, van bi cat.
  - Escape '^&': hong nang hon, dau mu lot vao URL thanh %5E.
  - Va nhanh `npx agent-browser`: nhanh do KHONG BAO GIO chay tren may nay,
    vi _find_agent_browser() tim thay node_modules/.bin truoc.

CACH SUA
--------
Sau khi `cmd_prefix` duoc dung xong, neu phan tu dau la .cmd/.bat tren Windows
thi thay bang [node.exe, <duong dan .js that>] - node.exe la executable that nen
CreateProcess goi thang, khong dinh cmd.exe, tham so di nguyen van.
Khong tim thay node hoac .js thi giu nguyen hanh vi cu (khong hong them).

MUC DO ANH HUONG
----------------
Meeting agent KHONG dung browser: platform `feishu` co toolsets
['clarify', 'meetings']. Chi platform `cli` moi bat `browser`.

CACH DUNG
---------
    python patch_browser_tool.py            # va (tu backup; tu don ban va cu)
    python patch_browser_tool.py --check    # chi kiem tra, khong ghi
    python patch_browser_tool.py --revert   # phuc hoi tu backup SOM NHAT (ban goc)

LUU Y: `hermes update` se ghi de file nay -> phai va lai.
"""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

TARGET = (
    Path(os.environ.get("LOCALAPPDATA", r"C:\Users\PC\AppData\Local"))
    / "hermes" / "hermes-agent" / "tools" / "browser_tool.py"
)

MARK = "HAPAS-PATCH"
HELPER_NAME = "_hapas_unwrap_win_shim"

# Ham helper, chen ngay truoc dinh nghia _find_agent_browser.
HELPER_ANCHOR = "def _find_agent_browser("

HELPER = f'''def {HELPER_NAME}(cmd_prefix):
    """{MARK}: doi npm .cmd shim -> [node.exe, <entry>.js] tren Windows.

    npm bin shim (.cmd) chay qua cmd.exe, ma cmd.exe bung `%*` khong nhay va coi
    '&' la dau tach lenh -> URL co query param bi cat cut am tham (vd Meta Ad
    Library chi con ?active_status=active). Bo nhay o tang Python hay escape
    caret deu vo dung vi shim bung lai them mot lan nua.

    Goi thang node.exe voi file .js that: executable that, khong dinh cmd.exe,
    tham so di nguyen van. Khong tim duoc thi tra ve nguyen xi.
    """
    if os.name != "nt" or not cmd_prefix:
        return cmd_prefix
    exe = str(cmd_prefix[0])
    if not exe.lower().endswith((".cmd", ".bat")):
        return cmd_prefix
    node = shutil.which("node")
    if not node:
        return cmd_prefix
    stem = os.path.splitext(os.path.basename(exe))[0]
    bindir = os.path.dirname(exe)
    # npm dat shim o <root>/node_modules/.bin/X.cmd, dich o
    # <root>/node_modules/X/bin/X.js (dung nhu ruot shim tu khai bao).
    candidates = [
        os.path.normpath(os.path.join(bindir, "..", stem, "bin", stem + ".js")),
        os.path.normpath(os.path.join(bindir, "..", stem, "bin", "cli.js")),
        os.path.normpath(os.path.join(bindir, "..", stem, "dist", "cli.js")),
    ]
    for js in candidates:
        if os.path.isfile(js):
            return [node, js] + list(cmd_prefix[1:])
    return cmd_prefix


'''

OLD_BLOCK = '''    else:
        cmd_prefix = [browser_cmd]
'''

NEW_BLOCK = f'''    else:
        cmd_prefix = [browser_cmd]
    cmd_prefix = {HELPER_NAME}(cmd_prefix)  # {MARK}
'''

# Ban va SAI cua lan truoc (nham vao nhanh npx khong bao gio chay) - can go bo.
STALE_MARK = "HERMES-PATCH (hapas_agent_social"


def _backups() -> list[Path]:
    return sorted(TARGET.parent.glob(TARGET.name + ".bak-pre-ampfix-*"))


def _clean_source() -> str:
    """Noi dung file da go moi ban va cu (uu tien backup som nhat = ban goc)."""
    s = TARGET.read_text(encoding="utf-8")
    if MARK not in s and STALE_MARK not in s:
        return s
    bk = _backups()
    if not bk:
        raise SystemExit("[FAIL] file da bi va nhung khong con backup goc de lam sach.")
    base = bk[0].read_text(encoding="utf-8")
    if MARK in base or STALE_MARK in base:
        raise SystemExit(f"[FAIL] backup som nhat ({bk[0].name}) cung da bi va.")
    print(f"  (dung backup goc {bk[0].name} lam nen, go ban va cu)")
    return base


def check() -> int:
    if not TARGET.exists():
        print(f"[FAIL] khong thay {TARGET}")
        return 1
    s = TARGET.read_text(encoding="utf-8")
    print(f"file          : {TARGET}")
    print(f"ban va dung   : {'CO' if MARK in s else 'CHUA'}  ({s.count(NEW_BLOCK)}/2 cho)")
    print(f"helper         : {'CO' if ('def ' + HELPER_NAME) in s else 'CHUA'}")
    if STALE_MARK in s:
        print("ban va CU (sai): CON - se duoc go khi chay lai")
    bk = _backups()
    print(f"backup goc    : {bk[0].name if bk else '(chua co)'}")

    node = shutil.which("node")
    print(f"\nnode          : {node}")
    try:
        sys.path.insert(0, str(TARGET.parent.parent))
        from tools.browser_tool import _find_agent_browser  # type: ignore
        bc = _find_agent_browser()
        print(f"browser_cmd   : {bc}")
        js = os.path.normpath(os.path.join(
            os.path.dirname(bc), "..", "agent-browser", "bin", "agent-browser.js"))
        print(f"entry .js     : {js}  ({'CO' if os.path.isfile(js) else 'THIEU'})")
    except Exception as e:
        print(f"browser_cmd   : (khong resolve duoc: {type(e).__name__}: {e})")
    return 0


def apply() -> int:
    src = _clean_source()
    n = src.count(OLD_BLOCK)
    if n != 2:
        print(f"[FAIL] ky vong 2 cho can sua, thay {n}. "
              "Hermes co the da doi code - dung va mu, kiem tra tay.")
        return 1
    if HELPER_ANCHOR not in src:
        print(f"[FAIL] khong thay moc '{HELPER_ANCHOR}' de chen helper.")
        return 1

    patched = src.replace(OLD_BLOCK, NEW_BLOCK)
    patched = patched.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = TARGET.with_name(TARGET.name + f".bak-pre-ampfix-{ts}")
    shutil.copy2(TARGET, bak)
    TARGET.write_text(patched, encoding="utf-8")

    r = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        shutil.copy2(bak, TARGET)
        print("[FAIL] py_compile loi -> DA TU DONG PHUC HOI. Chi tiet:")
        print(r.stderr.strip()[:800])
        return 1

    print(f"[ OK ] da va 2 cho + chen helper. Backup: {bak.name}")
    print("       Kiem tra: python patch_browser_tool.py --check")
    print("       Roi KHOI DONG LAI social agent de nap code moi.")
    return 0


def verify() -> int:
    """Im lang, chi tra exit code - de start.ps1 tu kiem tra luc khoi dong.

    0 = da va dung (helper + 2 cho goi)
    1 = CHUA va (rat co the vua chay `hermes update`, file bi ghi de)
    2 = khong thay file dich
    """
    if not TARGET.exists():
        return 2
    s = TARGET.read_text(encoding="utf-8")
    if ("def " + HELPER_NAME) in s and s.count(NEW_BLOCK) == 2:
        return 0
    return 1


def revert() -> int:
    bk = _backups()
    if not bk:
        print("[FAIL] khong thay backup nao.")
        return 1
    shutil.copy2(bk[0], TARGET)
    print(f"[ OK ] da phuc hoi ban GOC tu {bk[0].name}")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        sys.exit(check())
    if arg == "--verify":
        sys.exit(verify())
    if arg == "--revert":
        sys.exit(revert())
    if arg:
        print(__doc__)
        sys.exit(2)
    sys.exit(apply())
