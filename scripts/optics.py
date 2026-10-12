"""optics.py — 第2层：工程约束 + 参数规范化（纯 Python 确定性执行，LLM 不参与计算）

数据与 knowledge/optical.md、materials.md 一一对应；md 是 LLM 可读的说明，
本模块是可执行的同一份事实。修改时两处同步。
"""
import math

# --- 材料表（materials.md §1） ---
GLASSES = {
    "bk7":          {"name": "BK7",          "n_d": 1.5168, "abbe": 64.17, "density_g_cm3": 2.51},
    "k9":           {"name": "K9",           "n_d": 1.5168, "abbe": 64.17, "density_g_cm3": 2.51},
    "fused silica": {"name": "Fused Silica", "n_d": 1.4585, "abbe": 67.82, "density_g_cm3": 2.20},
    "jgs1":         {"name": "Fused Silica", "n_d": 1.4585, "abbe": 67.82, "density_g_cm3": 2.20},
    "sf11":         {"name": "SF11",         "n_d": 1.7847, "abbe": 25.68, "density_g_cm3": 4.74},
    "caf2":         {"name": "CaF2",         "n_d": 1.4338, "abbe": 94.99, "density_g_cm3": 3.18},
}

# --- 标准直径系列（optical.md §3） ---
STANDARD_DIAMETERS = [3, 5, 6, 8, 10, 12.5, 15, 18, 20, 25, 30, 35, 40, 50, 60, 75, 100]

# --- 中心厚度表（optical.md §4） ---
_CENTER_THICKNESS_TABLE = [(6, 1.5), (12.5, 2.5), (25, 4.0), (50, 5.0), (math.inf, 6.0)]

# --- 加工约束（optical.md §5） ---
MIN_EDGE_THICKNESS = {"standard": 1.0, "precision": 1.5}
SAG_RATIO_WARN = 0.85  # R/(D/2) 低于此值告警


class ConstraintError(ValueError):
    """无法自动修正的约束冲突，需用户做功能决策。"""


def get_glass(name):
    g = GLASSES.get(str(name).strip().lower())
    if g is None:
        raise ConstraintError(f"材料未知: {name}（支持: {sorted({v['name'] for v in GLASSES.values()})}）")
    return g


def standardize_diameter(d):
    """不在标准系列时向上取最接近标准值，返回 (D, 是否调整)。"""
    if d in STANDARD_DIAMETERS:
        return d, False
    for s in STANDARD_DIAMETERS:
        if s >= d:
            return s, True
    raise ConstraintError(f"直径 {d}mm 超出标准系列上限 100mm")


def center_thickness(d, tolerance="standard"):
    for limit, t in _CENTER_THICKNESS_TABLE:
        if d <= limit:
            return t if tolerance == "standard" else round(t * 0.8, 1)
    raise AssertionError


def derive_plano_convex(diameter_mm, focal_mm, material, tolerance="standard"):
    """平凸透镜参数推导 + 约束规范化。返回 (params, messages)。

    messages: (level, text) 列表，level ∈ info/warn/error，供用户确认时展示。
    """
    msgs = []
    glass = get_glass(material)
    n = glass["n_d"]

    # 标准约束：直径系列化
    D, adjusted = standardize_diameter(round(float(diameter_mm), 2))
    if adjusted:
        msgs.append(("warn", f"直径 {diameter_mm}mm 非标准值，已向上取标准直径 D={D}mm"))

    # 物理约束：薄透镜单球面近似
    R = round(focal_mm * (n - 1), 2)
    msgs.append(("info", f"R = f×(n-1) = {focal_mm}×({n}-1) = {R}mm（薄透镜近似，n_d={glass['name']}）"))

    # 几何推导：矢高
    r = D / 2.0
    if R < r:
        raise ConstraintError(f"R={R}mm 小于通光半径 {r}mm，球面不成立，请增大焦距或减小直径")
    sag = R - math.sqrt(R * R - r * r)

    if R / r < SAG_RATIO_WARN:
        msgs.append(("warn", f"R/(D/2)={R / r:.2f} < {SAG_RATIO_WARN}，接近半球，加工与装调风险高"))

    # 标准约束：中心厚度
    t_c = center_thickness(D, tolerance)

    # 加工约束：边缘厚度，不足则自动加厚
    t_min = MIN_EDGE_THICKNESS[tolerance]
    t_e = t_c - sag
    if t_e < t_min:
        t_c = math.ceil((sag + t_min) * 100) / 100  # 向上进位，保证 t_e ≥ t_min
        t_e = t_c - sag
        msgs.append(("warn", f"边缘厚度不足 {t_min}mm，中心厚度已加厚至 t_c={t_c}mm"))

    chamfer = 0.3 if D <= 50 else 0.5

    params = {
        "type": "plano_convex",
        "D": D, "f": focal_mm, "material": glass["name"], "n_d": n,
        "R": R, "sag": round(sag, 3),
        "t_c": t_c, "t_e": round(t_e, 3),
        "chamfer": chamfer, "tolerance": tolerance,
        "density_g_cm3": glass["density_g_cm3"],
    }
    return params, msgs


# --- NL 兜底提取（无 LLM 时可用；有 LLM 时由 LLM 提取，此函数仅做演示/校验） ---
import re


def nl_extract(text):
    """从中文描述提取平凸透镜意图。返回 dict 或 None（识别不出 → 交给 LLM）。"""
    m_d = re.search(r"[Φφ∅]\s*(\d+(?:\.\d+)?)", text)
    m_f = re.search(r"f\s*[=＝]\s*(\d+(?:\.\d+)?)", text, re.I)
    if not (m_d and m_f):
        return None
    material = None
    for key, g in GLASSES.items():
        if key in text.lower() or g["name"].lower() in text.lower():
            material = g["name"]
            break
    if material is None:
        return None
    lens_type = "plano_convex" if "平凸" in text else None
    if lens_type is None:
        return None
    tolerance = "precision" if ("精密" in text or "高精度" in text) else "standard"
    return {"type": lens_type, "D": float(m_d.group(1)), "f": float(m_f.group(1)),
            "material": material, "tolerance": tolerance}
