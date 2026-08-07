#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外觀 CAD → STEP 匯出（供 Onshape 匯入）
================================================================
OpenSCAD 匯不出 STEP——它是網格／CSG，不是 B-rep。所以這裡走：

    OpenSCAD 算繪 STL
      → OCCT 縫合三角面成殼、封成實體
      → ShapeUpgrade_UnifySameDomain 合併共面三角形成真正的平面
      → STEPCAFControl_Writer 寫出具名零件與組合件（AP214）

★這條路的界線，先講清楚★
  合併之後，★平面是真的平面★（一個 ADVANCED_FACE，不是幾百個三角形），
  但★圓孔與圓柱仍是多邊形近似★——OCCT 不會把多邊形反推回解析圓柱面。
  匯進 Onshape 之後是「匯入的實體」，可以組裝、量測、做圖，
  ★但不能參數化編輯尺寸★。要改尺寸請回頭改 params.scad 再重匯。
  細分預設用★自適應★（OpenSCAD 的 $fa/$fs）而不是固定 $fn：
  Ø110 的爐盆與 Ø4.5 的螺絲孔要是都切成 48 段，前者看得出稜線、後者又浪費面數。
  自適應讓段數隨弧長走——大圓分得細、小孔分得粗，檔案小又不醜。

★匯出後會自動把 STEP 讀回來驗一次★
  比對體積、實體有效性與零件數。看不到 Onshape 畫面，就只能這樣自證；
  「寫檔沒報錯」不等於「對方讀得到正確的東西」。

相依：OCCT 的 Python 綁定（cadquery-ocp）。
  系統 Python 受 PEP 668 保護，不可用 --break-system-packages（CLAUDE.md §2）。
  請裝在隔離的 venv 裡，★而且 venv 要放在 repo 之外★——
  放在專案目錄裡的話，run_tests.py 的測試探索會把 numpy 自帶的
  幾百個 test_*.py 全撿進來，自檢直接爆掉（2026-08-07 踩過）：
      python3 -m venv --without-pip ~/.venvs/ocp
      curl -sS https://bootstrap.pypa.io/get-pip.py | ~/.venvs/ocp/bin/python
      ~/.venvs/ocp/bin/python -m pip install cadquery-ocp
  然後用 ~/.venvs/ocp/bin/python 執行本檔。

用法（要用裝了 cadquery-ocp 的那個 venv 的 python 跑）：
  ~/.venvs/ocp/bin/python export_step.py                  # 零件 ＋ 元件 ＋ 組合件
  ~/.venvs/ocp/bin/python export_step.py --parts-only     # 只出列印件
  ~/.venvs/ocp/bin/python export_step.py --fa 3 --fs 0.3  # 更細（檔案更大）
  ~/.venvs/ocp/bin/python export_step.py --fn 48          # 改回固定段數
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
SCAD = HERE / "incense_burner.scad"
OUT = HERE / "STEP"

# 與 incense_burner.scad 的 PARTS_LIST / COMP_LIST 對應。
# ★這裡列名字，位置由 .scad 的 place() 決定★——不要在本檔重寫變換矩陣，
#   否則就是第二份真相來源，組裝圖與匯出的 STEP 會悄悄分岔。
PARTS = ["base", "chamber", "hood", "fan_mount", "sensor_pod",
         "socket_plate", "magnet_deck"]
COMPONENTS = ["bowl", "matrix_r4", "pi5", "d4184", "blower",
              "scd41", "sht31", "max6675", "tc_probe",
              "sleeves", "magnets", "mist", "hood_led"]

ZH = {
    "base": "電子艙底座", "chamber": "燃燒艙", "hood": "集煙罩",
    "fan_mount": "風扇座", "sensor_pod": "感測器艙",
    "bowl": "金屬爐盆(外購)", "matrix_r4": "MATRIX_Mini_R4(外購)",
    "pi5": "RaspberryPi5(外購)", "d4184": "D4184模組(外購)",
    "blower": "5015鼓風機(外購)", "scd41": "SCD41模組(外購)",
    "sht31": "SHT31模組(外購)", "max6675": "MAX6675板(外購)",
    "tc_probe": "K型熱電偶探頭(外購)",
    "socket_plate": "插孔板(理香機構)", "magnet_deck": "電磁鐵座(理香機構)",
    "sleeves": "導正套筒x5(外購)", "magnets": "電磁鐵x4(外購)",
    "mist": "超音波霧化模組(外購)", "hood_led": "罩內LED側光(外購)",
}

OPENSCAD_CANDIDATES = [
    "/mnt/c/Program Files/OpenSCAD/openscad.exe",
    "/mnt/c/Program Files (x86)/OpenSCAD/openscad.exe",
    "openscad",
]


def find_openscad():
    for c in OPENSCAD_CANDIDATES:
        if os.path.exists(c) or shutil.which(c):
            return c
    return None


def win_path(p: Path) -> str:
    s = str(p.resolve())
    if s.startswith("/mnt/") and len(s) > 6:
        return s[5].upper() + ":" + s[6:].replace("/", "\\")
    return s


def tess_args(a):
    """細分設定。$fn=0 時 OpenSCAD 才會改用 $fa/$fs。"""
    if a.fn:
        return ["-D", f"$fn={a.fn}"]
    # BOWL_FN=0 讓爐盆也回歸自適應（預覽時它固定 160 段，匯出用不到那麼細）
    return ["-D", "$fn=0", "-D", f"$fa={a.fa}", "-D", f"$fs={a.fs}",
            "-D", "BOWL_FN=0"]


def render_stl(exe, name, dst, tess, placed):
    """算繪單一零件／元件的 STL。placed=True 取組裝定位後的位置。"""
    is_exe = exe.endswith(".exe")
    # ★一律走 solo/placed 這兩個分派★ 不要用 part="<名稱>"：
    #   那只對 5 個列印件有效，元件會掉進 dispatch 的預設分支。
    args = ["-D", 'part="placed"' if placed else 'part="solo"',
            "-D", f'PAIR_A="{name}"']
    cmd = [exe, "-o", win_path(dst) if is_exe else str(dst),
           *tess, *args,
           win_path(SCAD) if is_exe else str(SCAD)]
    r = subprocess.run(cmd, capture_output=True, timeout=900)
    err = (r.stderr or b"").decode("utf-8", errors="replace")
    for pat in ("Ignoring unknown variable", "undefined operation",
                "Unable to convert", "Can't open include file"):
        if pat in err:
            line = next((l.strip() for l in err.splitlines() if pat in l), pat)
            raise RuntimeError(f"{name}: OpenSCAD 回報「{line}」")
    if not dst.exists() or dst.stat().st_size < 200:
        raise RuntimeError(f"{name}: 算繪不出幾何")
    return dst


def stl_volume(path: Path) -> float:
    """
    用散度定理直接從 STL 三角形算體積——★刻意不經過 OCCT★。
    這是要拿來跟 OCCT 的結果對照的，共用同一套程式碼就失去交叉驗證的意義。
    """
    import struct
    data = path.read_bytes()
    v = 0.0
    if data[:5].lower() != b"solid" or b"facet" not in data[:512]:
        n = struct.unpack("<I", data[80:84])[0]
        for i in range(n):
            o = 84 + i * 50 + 12
            a, b, c = (struct.unpack("<3f", data[o + j * 12:o + 12 + j * 12])
                       for j in range(3))
            v += (a[0] * (b[1] * c[2] - b[2] * c[1])
                  - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    else:
        import re
        pts = [tuple(map(float, m.groups()))
               for m in re.finditer(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)]
        for i in range(0, len(pts) - 2, 3):
            a, b, c = pts[i], pts[i + 1], pts[i + 2]
            v += (a[0] * (b[1] * c[2] - b[2] * c[1])
                  - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return abs(v)


# ── OCCT ────────────────────────────────────────────────────────
def _occ():
    try:
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import (BRepBuilderAPI_Sewing,
                                        BRepBuilderAPI_MakeSolid)
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        from OCP.Interface import Interface_Static
        from OCP.RWStl import RWStl
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDF import TDF_Label
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopoDS import TopoDS_Shape, TopoDS
        from OCP.TopAbs import TopAbs_ShapeEnum
        from OCP.TopExp import TopExp_Explorer
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.IFSelect import IFSelect_ReturnStatus
        from OCP.Message import Message, Message_Gravity
        return locals()
    except Exception as e:  # noqa: BLE001
        print("找不到 OCCT 的 Python 綁定（cadquery-ocp）。")
        print("本檔開頭有安裝步驟——請在隔離的 venv 裡裝，不要動系統 Python。")
        print(f"（原始錯誤：{type(e).__name__}: {e}）")
        sys.exit(2)


def stl_to_solid(O, stl_path: Path, name: str, report):
    """
    STL → B-rep 實體 → 合併共面面。

    ★不用「逐三角形建面再縫合」★ 那條路要猜縫合容差：太緊則該共用的邊沒接起來
    （殼有破洞 → BRepCheck 判定無效），太鬆則會把不該合的頂點併掉。
    2026-08-06 base 就是這樣壞的：縫合完 BRepCheck 直接說 invalid，
    而 OpenSCAD 那邊 Volumes=2、Simple=yes 全過——兩套工具對「有效」的定義不同。

    改成★由共用拓樸直接建構★：
      每個節點建一個 TopoDS_Vertex、每條無向邊建一個 TopoDS_Edge，各只建一次，
      三角形面直接引用它們。這樣「相鄰面共用同一條邊」是建構出來的事實，
      不是容差比對的結果，也就沒有容差可猜。
    """
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeVertex,
                                    BRepBuilderAPI_MakeEdge,
                                    BRepBuilderAPI_MakeWire,
                                    BRepBuilderAPI_MakeFace)
    from OCP.TopoDS import TopoDS_Shell, TopoDS_Solid
    from OCP.ShapeFix import ShapeFix_Shape

    tri = O["RWStl"].ReadFile_s(str(stl_path))
    if tri is None:
        raise RuntimeError(f"{name}: STL 讀不進來")

    n_node, n_tri = tri.NbNodes(), tri.NbTriangles()
    verts = [None] + [BRepBuilderAPI_MakeVertex(tri.Node(i)).Vertex()
                      for i in range(1, n_node + 1)]
    edges = {}

    def edge(i, j):
        """回傳從 i 指向 j 的邊。無向邊只建一次，反向時取 Reversed()。"""
        key = (i, j) if i < j else (j, i)
        e = edges.get(key)
        if e is None:
            e = BRepBuilderAPI_MakeEdge(verts[key[0]], verts[key[1]]).Edge()
            edges[key] = e
        # Reversed() 回傳的是 TopoDS_Shape，要轉回 Edge 才能組 Wire
        return e if i < j else O["TopoDS"].Edge_s(e.Reversed())

    b = BRep_Builder()
    shell = TopoDS_Shell()
    b.MakeShell(shell)

    n_face = n_skip = 0
    for k in range(1, n_tri + 1):
        a, c, d = tri.Triangle(k).Get()
        if a == c or c == d or d == a:
            n_skip += 1
            continue
        pa, pc, pd = tri.Node(a), tri.Node(c), tri.Node(d)
        # 退化（三點共線／零面積）的三角形做不出面，也不影響封閉性
        if pa.IsEqual(pc, 1e-9) or pc.IsEqual(pd, 1e-9) or pd.IsEqual(pa, 1e-9):
            n_skip += 1
            continue
        w = BRepBuilderAPI_MakeWire(edge(a, c), edge(c, d), edge(d, a))
        if not w.IsDone():
            n_skip += 1
            continue
        f = BRepBuilderAPI_MakeFace(w.Wire(), True)   # True = 只找平面
        if not f.IsDone():
            n_skip += 1
            continue
        b.Add(shell, f.Face())
        n_face += 1

    if n_skip:
        raise RuntimeError(
            f"{name}: 有 {n_skip}/{n_tri} 個三角形建不出面——"
            f"殼會有破洞，不輸出（避免下游拿到壞檔）")

    shell.Closed(True)
    solid = TopoDS_Solid()
    b.MakeSolid(solid)
    b.Add(solid, shell)

    # ★先修再合併★ 順序是量出來的，不是猜的（2026-08-06 對 base 實測）：
    #     原始           → invalid
    #     直接合併       → invalid
    #     合併後再修     → invalid
    #     ★先修再合併★ → valid（1707 面，體積不變）
    #   base 是特徵最多的零件（螺柱、柵格、榫、螺柱座、後面板開孔），
    #   細長三角形讓平面擬合條件變差，其他四件用同一條路都直接就有效。
    fx0 = ShapeFix_Shape(solid)
    fx0.Perform()
    fixed = fx0.Shape()

    # ★合併共面三角形★ 這一步決定 STEP 好不好用：
    #   不做的話 base 是好幾千個三角面，做完剩下真正的平面。
    uni = O["ShapeUpgrade_UnifySameDomain"](fixed, True, True, True)
    uni.Build()
    merged = uni.Shape()

    def count_faces(sh):
        e = O["TopExp_Explorer"](sh, O["TopAbs_ShapeEnum"].TopAbs_FACE)
        n = 0
        while e.More():
            n += 1
            e.Next()
        return n

    before, after = count_faces(solid), count_faces(merged)

    if not O["BRepCheck_Analyzer"](merged).IsValid():
        fx1 = ShapeFix_Shape(merged)
        fx1.SetPrecision(1e-5)
        fx1.SetMaxTolerance(1e-3)
        fx1.Perform()
        merged = fx1.Shape()
        after = count_faces(merged)

    props = O["GProp_GProps"]()
    O["BRepGProp"].VolumeProperties_s(merged, props)
    vol = props.Mass()

    # ★獨立的體積交叉比對★
    #   OCCT 說「有效」只代表拓樸自洽，不保證幾何跟來源一樣。
    #   這裡用散度定理直接從 STL 三角形算一次體積（跟 OCCT 完全不同的路徑），
    #   兩邊對不上就表示轉檔過程中形狀被改動了——那比檔案壞掉更難察覺。
    ref = stl_volume(stl_path)
    drift = abs(vol - ref) / ref if ref else 0.0
    if drift > 1e-4:
        raise RuntimeError(
            f"{name}: 轉成 B-rep 後體積變了 {drift:.3%}"
            f"（STL {ref:,.1f}mm³ vs OCCT {vol:,.1f}mm³）——形狀被動到了，不輸出")

    ok = O["BRepCheck_Analyzer"](merged).IsValid()
    report.append((name, n_tri, before, after, vol, ok))
    if not ok:
        raise RuntimeError(f"{name}: OCCT 判定實體無效，不輸出（避免下游拿到壞檔）")
    return merged


def write_step(O, items, dst: Path, doc_name: str, as_assembly: bool):
    """
    items = [(名稱, shape)]

    as_assembly=True 時建成真正的 product 結構（一個母件底下掛具名子件），
    而不是把好幾個實體平鋪在同一層——Onshape 匯入後才會是組合件而不是散裝零件。
    """
    from OCP.TopoDS import TopoDS_Compound
    doc = O["TDocStd_Document"](O["TCollection_ExtendedString"]("XmlOcaf"))
    tool = O["XCAFDoc_DocumentTool"].ShapeTool_s(doc.Main())

    if as_assembly:
        # ★不要靠「元件順序＝加入順序」配名字★
        #   先前用 GetComponents_s 取回子標籤再依索引命名，但那個順序不保證
        #   與加入順序一致——結果有一個子件掛著 OCCT 的預設名 "SOLID"
        #   而真正的名稱掉了（2026-08-07 回讀驗證抓到）。
        #   改成標準 XCAF 作法：每個形狀各自建一個具名零件標籤，
        #   再明確掛成母件的元件。名字與形狀的對應是建構出來的，不是猜的。
        from OCP.TopLoc import TopLoc_Location
        root = tool.NewShape()
        O["TDataStd_Name"].Set_s(root, O["TCollection_ExtendedString"](doc_name))
        for name, shape in items:
            nm = O["TCollection_ExtendedString"](name)
            part = tool.AddShape(shape, False)          # 零件本體
            O["TDataStd_Name"].Set_s(part, nm)
            comp = tool.AddComponent(root, part, TopLoc_Location())
            O["TDataStd_Name"].Set_s(comp, nm)          # 實例也給同一個名字
        tool.UpdateAssemblies()
    else:
        for name, shape in items:
            lab = tool.AddShape(shape, False)
            O["TDataStd_Name"].Set_s(lab, O["TCollection_ExtendedString"](name))

    O["Interface_Static"].SetCVal_s("write.step.unit", "MM")
    O["Interface_Static"].SetCVal_s("write.step.schema", "AP214IS")
    O["Interface_Static"].SetIVal_s("write.step.assembly", 1 if as_assembly else 0)
    O["Interface_Static"].SetCVal_s("write.step.product.name", doc_name)

    w = O["STEPCAFControl_Writer"]()
    w.SetNameMode(True)
    from OCP.STEPControl import STEPControl_StepModelType
    w.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)
    status = w.Write(str(dst))
    from OCP.IFSelect import IFSelect_ReturnStatus
    if status != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError(f"{dst.name}: STEP 寫入失敗（狀態 {status}）")
    return dst


def iso10303_escape(path: Path):
    """
    把 STEP 字串字面量裡的非 ASCII 改成 ISO 10303-21 的 \\X2\\<UTF-16BE hex>\\X0\\ 編碼。

    ★為什麼要做★ ISO 10303-21 的字串字面量只允許 ASCII，非 ASCII 必須用控制指令
    編碼。OCCT 沒有這樣做，寬容的讀取器看得懂、嚴格的會顯示成亂碼——
    而我看不到 Onshape 畫面，不能賭它屬於哪一種。

    ★而且 OCCT 寫出來的是「雙重編碼」★（2026-08-06 量到的）：
      「集煙罩」的 UTF-8 應該是 e9 9b 86 e7 85 99 e7 bd a9（9 bytes），
      檔案裡卻是 c3 a9 c2 9b c2 86 …（18 bytes）——
      它把 UTF-8 的每個位元組當成一個字元，然後又編了一次 UTF-8。
      所以要先 latin-1 反編一層，才拿得到真正的字。
    """
    text = path.read_bytes().decode("utf-8")
    out, buf = [], []
    i, n, in_str = 0, len(text), False

    def flush():
        if not buf:
            return
        lit = "".join(buf)
        buf.clear()
        # 先解開 OCCT 的雙重編碼。純 ASCII 的字面量走這一步不會有任何變化。
        try:
            lit = lit.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        seg, cur = [], []

        def dump():
            if cur:
                seg.append("\\X2\\"
                           + "".join(ch.encode("utf-16-be").hex().upper()
                                     for ch in cur)
                           + "\\X0\\")
                cur.clear()

        for ch in lit:
            if ord(ch) < 128:
                dump()
                seg.append(ch)
            else:
                cur.append(ch)
        dump()
        out.append("".join(seg))

    while i < n:
        c = text[i]
        if not in_str:
            out.append(c)
            in_str = (c == "'")
            i += 1
        elif c == "'":
            if i + 1 < n and text[i + 1] == "'":   # STEP 用 '' 表示字串裡的單引號
                buf.append("''")
                i += 2
                continue
            flush()
            out.append("'")
            in_str = False
            i += 1
        else:
            buf.append(c)
            i += 1
    flush()
    path.write_bytes("".join(out).encode("ascii"))


def step_names(path: Path):
    """把 STEP 讀回來，取出所有 PRODUCT 名稱（Onshape 拿來當零件名的就是它）。"""
    import re
    raw = path.read_bytes().decode("ascii")
    names = []
    # ★要容許換行★ STEP 會把長實體折行，PRODUCT( 與名稱之間可能隔著
    #   換行與空白。第一版沒容許，於是折到下一行的名稱一律讀不到——
    #   檔案其實是好的，錯的是讀取器（2026-08-07 回讀驗證誤報霧化模組缺名）。
    for m in re.finditer(r"PRODUCT\(\s*'((?:[^']|'')*)'", raw):
        t = m.group(1).replace("''", "'")
        # 還原 \X2\<hex>\X0\
        t = re.sub(r"\\X2\\((?:[0-9A-F]{4})+)\\X0\\",
                   lambda mm: bytes.fromhex(mm.group(1)).decode("utf-16-be"), t)
        names.append(t)
    return sorted(set(names))


def n_solids(O, shape) -> int:
    """數實體個數。★不能假設「一個具名零件＝一個實體」★——
    導正套筒與電磁鐵各是 4 件一組，本來就該是 4 個實體。"""
    e = O["TopExp_Explorer"](shape, O["TopAbs_ShapeEnum"].TopAbs_SOLID)
    n = 0
    while e.More():
        n += 1
        e.Next()
    return n


def verify_step(O, path: Path, want_vol, want_parts):
    """
    ★把寫出去的 STEP 讀回來驗★
    看不到 Onshape 畫面，「寫檔沒報錯」不等於「對方讀得到正確的東西」。
    這裡驗三件事：讀得進來、實體有效、體積與來源一致、零件數對。
    """
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_ReturnStatus
    r = STEPControl_Reader()
    if r.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        return f"讀不回來"
    r.TransferRoots()
    shape = r.OneShape()
    if shape.IsNull():
        return "讀回來是空的"

    exp = O["TopExp_Explorer"](shape, O["TopAbs_ShapeEnum"].TopAbs_SOLID)
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    if n != want_parts:
        return f"零件數 {n}，應為 {want_parts}"

    props = O["GProp_GProps"]()
    O["BRepGProp"].VolumeProperties_s(shape, props)
    got = props.Mass()
    if want_vol > 0 and abs(got - want_vol) / want_vol > 0.001:
        return f"體積 {got:,.0f}mm³ 與來源 {want_vol:,.0f}mm³ 差 {abs(got-want_vol)/want_vol:.2%}"
    if not O["BRepCheck_Analyzer"](shape).IsValid():
        return "讀回來的實體無效"
    return None


def main():
    ap = argparse.ArgumentParser(description="外觀 CAD → STEP（供 Onshape 匯入）")
    ap.add_argument("--fn", type=int, default=0,
                    help="固定圓弧段數。0（預設）＝改用 --fa/--fs 自適應")
    ap.add_argument("--fa", type=float, default=6.0,
                    help="自適應：每段最大角度（預設 6°→ 整圓最多 60 段）")
    ap.add_argument("--fs", type=float, default=0.6,
                    help="自適應：每段最小弦長 mm（預設 0.6）")
    ap.add_argument("--parts-only", action="store_true",
                    help="只輸出列印件，不含外購元件")
    args = ap.parse_args()

    exe = find_openscad()
    if not exe:
        print("找不到 OpenSCAD，無法算繪 STL")
        sys.exit(1)

    O = _occ()
    OUT.mkdir(exist_ok=True)
    names = PARTS + ([] if args.parts_only else COMPONENTS)

    # ★暫存放在 .scad 旁邊★ Windows 的 openscad.exe 看不到 WSL 的 /tmp
    tmp = Path(tempfile.mkdtemp(prefix=".stepexp_", dir=HERE))
    report, failures = [], []
    solo, placed = {}, {}

    tess = tess_args(args)
    print("算繪 STL（" + " ".join(t for t in tess if t != "-D") + "）…")

    try:
        for nm in names:
            t0 = time.time()
            # ★立即輸出★ 不 flush 的話輸出會被緩衝，看不出卡在哪個零件
            print(f"  {nm:<12}", end="", flush=True)
            try:
                # 單件：原點在零件自己的座標系，給 Onshape 當獨立零件用
                render_stl(exe, nm, tmp / f"s_{nm}.stl", tess, placed=False)
                # 定位件：套用 place()，給組合件用
                render_stl(exe, nm, tmp / f"p_{nm}.stl", tess, placed=True)
            except Exception as e:  # noqa: BLE001
                print("算繪失敗", flush=True)
                failures.append(f"{nm}: {e}")
                continue
            t1 = time.time()

            try:
                solo[nm] = stl_to_solid(O, tmp / f"s_{nm}.stl", nm, report)
                placed[nm] = stl_to_solid(O, tmp / f"p_{nm}.stl", nm + "@placed", [])
                print(f"算繪 {t1-t0:5.1f}s　轉檔 {time.time()-t1:5.1f}s", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"轉檔失敗（算繪 {t1-t0:.1f}s）", flush=True)
                failures.append(f"{nm}: {e}")

        print("\n寫出 STEP…")
        vols = {nm: v for nm, _, _, _, v, _ in report}
        for nm, shape in solo.items():
            f = OUT / f"{nm}_{ZH[nm]}.step"
            write_step(O, [(ZH[nm], shape)], f, ZH[nm], as_assembly=False)
            iso10303_escape(f)
            # 期望實體數由來源形狀本身數出來，不是寫死 1
            bad = verify_step(O, f, vols.get(nm, 0), n_solids(O, shape))
            if not bad and ZH[nm] not in step_names(f):
                bad = f"零件名稱在檔案裡還原不出來（讀到 {step_names(f)}）"
            print(f"  {f.name:<34}{f.stat().st_size/1024:>7.0f} KB  "
                  f"{'✓ 回讀驗證通過' if not bad else '✗ ' + bad}")
            if bad:
                failures.append(f"{f.name}: 回讀驗證 — {bad}")

        if placed:
            f = OUT / "智慧香爐_組合件.step"
            asm_vol = 0.0
            pr = O["GProp_GProps"]()
            for sh in placed.values():
                q = O["GProp_GProps"]()
                O["BRepGProp"].VolumeProperties_s(sh, q)
                asm_vol += q.Mass()
            write_step(O, [(ZH[n], s) for n, s in placed.items()], f,
                       "智慧香爐", as_assembly=True)
            iso10303_escape(f)
            bad = verify_step(O, f, asm_vol,
                              sum(n_solids(O, sh) for sh in placed.values()))
            if not bad:
                got = step_names(f)
                missing = [ZH[n] for n in placed if ZH[n] not in got]
                if missing:
                    bad = f"這些零件名稱還原不出來：{missing}"
            print(f"  {f.name:<34}{f.stat().st_size/1024:>7.0f} KB  "
                  f"{'✓ 回讀驗證通過（' + str(len(placed)) + ' 個具名零件）' if not bad else '✗ ' + bad}")
            if bad:
                failures.append(f"組合件: 回讀驗證 — {bad}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 68)
    print(f"{'零件':<22}{'三角面':>8}{'縫合面':>8}{'合併後':>8}{'體積mm³':>12}  有效")
    print("-" * 68)
    for nm, ntri, before, after, vol, ok in report:
        print(f"{nm:<22}{ntri:>8}{before:>8}{after:>8}{vol:>12,.0f}  "
              f"{'✓' if ok else '✗'}")
    print("=" * 68)
    print("★圓孔／圓柱在 STEP 裡是多邊形近似，不是解析曲面★")
    print("  細分：" + (" ".join(t for t in tess if t != "-D")))
    print("  要改尺寸請回 params.scad 重匯，不要在 Onshape 直接改——"
          "那邊改了不會回流到這裡。")

    if failures:
        print("\n失敗：")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
