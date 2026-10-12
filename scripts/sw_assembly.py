"""sw_assembly.py — 装配体框架（第3层特征级抽象 v1）

能力：
  - 新建装配体（自动找 *.asmdot 模板）
  - 插入零部件（AddComponent4，指定初始位置）
  - 按几何属性反查配合实体（圆柱面半径 / 平面法向），不依赖视角坐标拾取
  - 添加配合（重合/同轴心/距离/角度，AddMate3，错误码回读）
  - 校验配合状态并保存 .SLDASM

配合类型枚举（swconst.tlb 官方值）：
  coincident=0, concentric=1, distance=5, angle=6
对齐枚举：aligned=0, anti=1, closest=2
"""
import os

import pythoncom
from win32com.client import VARIANT

import sw_core

MATE_TYPES = {"coincident": 0, "concentric": 1, "distance": 5, "angle": 6}
ALIGN = {"aligned": 0, "anti": 1, "closest": 2}


def new_assembly(sw, template=None):
    if template is None:
        template = _find_asm_template(sw)
    try:
        sw.SetUserPreferenceToggle(111, True)  # 始终用默认模板，免弹窗
    except Exception:
        pass
    model = sw.NewDocument(template, 0, 0, 0)
    if model is None:
        import time
        for _ in range(20):
            model = sw.ActiveDoc
            if model is not None:
                break
            time.sleep(0.25)
    if model is None:
        raise RuntimeError("新建装配体失败")
    if int(sw_core.com_get(model, "GetType")) != 2:
        raise RuntimeError("新建的文档不是装配体")
    return sw_core._early(model, "IModelDoc2")


def _find_asm_template(sw):
    """装配体模板：与零件模板共用 sw_core 的解析顺序（含版本匹配兜底）。"""
    return sw_core.find_template(sw, ".asmdot")


def _as_asm(asm):
    return sw_core._early(asm, "IAssemblyDoc")


def insert_component(asm, path, at=(0.0, 0.0, 0.0), sw=None):
    """插入零部件（米），返回早绑定 IComponent2。
    AddComponent4 在零件未加载进内存时可能静默返回 None（SW2018 实测），
    此时先 OpenDoc6 加载零件、激活装配体后重试。"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if sw is None:
        sw = sw_core.connect()
    adoc = _as_asm(asm)
    comp = adoc.AddComponent4(path, "", float(at[0]), float(at[1]), float(at[2]))
    if comp is None:
        dyn_sw = sw_core._dyn(sw)
        errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        dyn_sw.OpenDoc6(path, 1, 0, "", errs, warns)  # 1 = swDocPART
        dyn_sw.ActivateDoc2(sw_core.com_get(asm, "GetTitle"), False, errs)
        comp = adoc.AddComponent4(path, "", float(at[0]), float(at[1]), float(at[2]))
    if comp is None:
        raise RuntimeError(f"插入零部件失败: {path}")
    return sw_core._early(comp, "IComponent2")


def _faces_of(comp):
    body = comp.GetBody()
    if body is None:
        raise RuntimeError(f"零部件 {comp.Name2} 没有实体（装配特征/轻化？）")
    return [sw_core._early(f, "IFace2") for f in (body.GetFaces() or [])]


def find_face(comp, kind, radius_mm=None, normal=None, select="first", root_mm=None):
    """按几何属性反查面（在零件局部空间判断，变换无关）。

    kind: "cylinder"（按半径筛选）| "plane"（按法向筛选，方向性：法向需同向，反向请取负）
    normal: [nx,ny,nz]，单位向量容差 1e-3
    root_mm: [x,y,z]，仅平面：根点与该点距离 <0.2mm 才匹配（精确定位唯一面）
    select: "first" | "largest" | "smallest"（largest/smallest 仅平面按面积排序）
    返回 (IFace2, 描述dict)；找不到返回 (None, {...})。
    """
    matches = []
    for face in _faces_of(comp):
        surf = sw_core._early(face.GetSurface(), "ISurface")
        if kind == "cylinder" and surf.IsCylinder():
            p = surf.CylinderParams  # [root xyz, axis xyz, radius]
            r_mm = float(p[6]) * 1000.0
            if radius_mm is None or abs(r_mm - radius_mm) < 0.01:
                matches.append((face, {"kind": "cylinder", "radius_mm": round(r_mm, 4),
                                       "axis": [round(v, 4) for v in p[3:6]]}))
        elif kind == "plane" and surf.IsPlane():
            p = surf.PlaneParams  # 本机 SW2018 实测布局: [法向 xyz, 根点 xyz]
            n = p[0:3]
            root = [v * 1000.0 for v in p[3:6]]
            if normal is not None and not _is_parallel(n, normal):
                continue
            if root_mm is not None:
                dist = sum((a - b) ** 2 for a, b in zip(root, root_mm)) ** 0.5
                if dist >= 0.2:
                    continue
            area = 0.0
            try:
                area = float(face.GetArea())
            except Exception:
                pass
            matches.append((face, {"kind": "plane",
                                   "normal": [round(v, 4) for v in n],
                                   "root_mm": [round(v, 3) for v in root],
                                   "area_mm2": round(area * 1e6, 2)}))
    if not matches:
        return None, {"kind": kind, "radius_mm": radius_mm, "normal": normal,
                      "root_mm": root_mm, "error": "未找到匹配面"}
    if select == "largest" and kind == "plane":
        matches.sort(key=lambda m: -m[1].get("area_mm2", 0))
    elif select == "smallest" and kind == "plane":
        matches.sort(key=lambda m: m[1].get("area_mm2", 0))
    return matches[0]


def _is_parallel(a, b, tol=1e-3):
    """方向性平行判断：只认同向（点积为正）。要匹配反向面，在 spec 里把法向取负。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na < 1e-9 or nb < 1e-9:
        return False
    return abs(dot / (na * nb) - 1.0) < tol


def add_mate(asm, face1, face2, mtype, align="closest", distance_m=0.0, flip=False):
    """对两个面加配合。返回 (mate, error_code)。
    error_code 为 swAddMateError_e：1=NoError(成功) 2=类型错 3=对齐错 4=选择错 5=过定义。"""
    type_code = MATE_TYPES[mtype] if isinstance(mtype, str) else int(mtype)
    align_code = ALIGN[align] if isinstance(align, str) else int(align)

    sel_mgr = sw_core._early(asm.SelectionManager, "ISelectionMgr")
    asm.ClearSelection2(True)
    d1 = sel_mgr.CreateSelectData(); d1.Mark = 1
    d2 = sel_mgr.CreateSelectData(); d2.Mark = 1
    e1 = sw_core._early(face1, "IEntity")
    e2 = sw_core._early(face2, "IEntity")
    if not e1.Select4(False, d1):
        raise RuntimeError("配合实体1选择失败")
    if not e2.Select4(True, d2):
        raise RuntimeError("配合实体2选择失败")

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    # AddMate3 末参为 byref out；makepy 早绑定不接受 VARIANT 占位，须走后期绑定
    asm_dyn = sw_core._dyn(_as_asm(asm))
    mate = asm_dyn.AddMate3(type_code, align_code, bool(flip), float(distance_m),
                            0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, False, errors)
    asm.ClearSelection2(True)
    return mate, int(errors.value)


def check_mates(asm):
    """遍历配合组，汇报配合数量与文档重建状态。"""
    feat = asm.FirstFeature()
    mate_count = 0
    mate_names = []
    while feat is not None:
        feat = sw_core._early(feat, "IFeature")
        if feat.GetTypeName2() == "MateGroup":
            sub = feat.GetFirstSubFeature()
            while sub is not None:
                sub = sw_core._early(sub, "IFeature")
                mate_count += 1
                mate_names.append(sub.Name)
                sub = sub.GetNextSubFeature()
        feat = feat.GetNextFeature()
    asm.ForceRebuild3(False)
    return {"mate_count": mate_count, "mates": mate_names}
