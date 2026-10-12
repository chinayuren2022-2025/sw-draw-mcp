"""sw_config.py — 零件级配置/方程式/设计表层（补全清单 5.1/5.2/5.3）

目标环境：Windows + pywin32 311 + SolidWorks 2018（TLB v26）。
当前开发环境无法调用 COM：所有不确定签名采用多候选回退，标注
“待 SW2018 实测”，由 scripts/tests/integration_sw2018.py 驱动修正。
"""
import sw_core

_PUBLIC = []


def _pub(fn):
    _PUBLIC.append(fn.__name__)
    return fn


def _cm(model):
    """IConfigurationManager（早绑定包装 + 后期绑定回退）。"""
    try:
        return sw_core._early(model.ConfigurationManager, "IConfigurationManager")
    except Exception:
        return sw_core._dyn(model).ConfigurationManager


@_pub
def add_configuration(model, name, comment="", alternate_name="",
                      parent_config="", activate=True):
    """新建配置。返回配置名。

    SW2018 v26 实测：用 IConfigurationManager::AddConfiguration2
    (Name, Comment, AlternateName, Options, ParentConfigName, Description, Rebuild)，
    新建后自动激活新配置；model.ShowConfiguration2 对已激活配置返回 False 属正常。
    """
    name = str(name)
    cm = _cm(model)
    dyn = sw_core._dyn(cm)
    for args in ((name, comment, alternate_name, 0, parent_config, comment, True),
                 (name, comment, alternate_name, 0, parent_config, comment)):
        try:
            cfg = dyn.AddConfiguration2(*args)
            if cfg is not None:
                if activate:
                    show_configuration(model, name)
                return name
        except Exception as exc:
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"add_configuration({name!r}) 失败: {exc}") from exc
    raise RuntimeError(f"add_configuration({name!r}): AddConfiguration2 所有候选签名失败")


@_pub
def show_configuration(model, name):
    """激活配置。ShowConfiguration2 返回 False 时检查活动配置名，已激活即成功。"""
    name = str(name)
    dyn = sw_core._dyn(model)
    for args in ((name,), (name, 0)):
        try:
            ret = dyn.ShowConfiguration2(*args)
            if ret is None or ret:
                return name
        except Exception as exc:
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"show_configuration({name!r}) 失败: {exc}") from exc
    try:
        active = _cm(model).ActiveConfiguration
        if active is not None and str(active.Name) == name:
            return name
    except Exception:
        pass
    try:
        ret = dyn.ShowConfiguration(name)
        if ret is None or ret:
            return name
    except Exception as exc:
        raise RuntimeError(f"show_configuration({name!r}) 失败: {exc}") from exc
    raise RuntimeError(f"show_configuration({name!r}) 返回 False")


activate_configuration = show_configuration


@_pub
def delete_configuration(model, name):
    """删除配置（活动配置不可删）。IConfigurationManager::DeleteConfiguration2。"""
    cm = _cm(model)
    dyn = sw_core._dyn(cm)
    for args in ((str(name), 0), (str(name),)):
        try:
            if dyn.DeleteConfiguration2(*args):
                return True
        except Exception as exc:
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"delete_configuration({name!r}) 失败: {exc}") from exc
    raise RuntimeError(f"delete_configuration({name!r}): 删除失败或配置不存在")


@_pub
def list_configurations(model):
    """返回配置名列表。"""
    cm = _cm(model)
    dyn = sw_core._dyn(cm)
    for method in ("GetConfigurationNames", "GetConfigurationNameArray"):
        try:
            names = getattr(dyn, method)()
            if names:
                return [str(n) for n in names]
        except Exception:
            continue
    try:
        n = int(dyn.GetConfigurationCount())
        out = []
        for i in range(n):
            try:
                out.append(str(dyn.GetConfigurationName(i)))
            except Exception:
                pass
        if out:
            return out
    except Exception:
        pass
    active = cm.ActiveConfiguration
    if active is not None:
        return [str(active.Name)]
    raise RuntimeError("list_configurations 失败: 无法枚举配置")


def _eqm(model):
    try:
        return sw_core._early(model.GetEquationMgr(), "IEquationMgr")
    except Exception:
        return sw_core._dyn(model).GetEquationMgr()


@_pub
def add_equation(model, expression):
    """添加方程式。expression 为 SW 方程式字符串，如
    '"D1@Sketch1" = "D2@Sketch1" * 2' 或 '"x" = 12.5mm'。

    SW2018 v26 实测签名：
      Add3(Index, Equation, Solve, WhichConfigurations, ConfigNames)
      Add2(Index, Equation, Solve)
    """
    eqm = _eqm(model)
    dyn = sw_core._dyn(eqm)
    expr = str(expression)
    for args in ((0, expr, True, 2, ""), (0, expr, True, 0, ""),
                 (0, expr, True), (0, expr)):
        try:
            if len(args) >= 5:
                ret = dyn.Add3(*args)
            elif len(args) == 3:
                ret = dyn.Add2(*args)
            else:
                ret = dyn.Add(*args)
            if ret is not None:
                return ret
        except Exception as exc:
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"add_equation({expr!r}) 失败: {exc}") from exc
    raise RuntimeError(f"add_equation({expr!r}): 所有候选签名失败")


@_pub
def add_global_variable(model, name, value, unit="mm"):
    """添加/更新全局变量（实现为方程式 '<name>' = <value><unit>）。"""
    expr = f'"{name}" = {float(value)}{unit}'
    add_equation(model, expr)
    return name


@_pub
def rebuild_equations(model):
    """重新求值方程式（IEquationMgr::EvaluateAll）。"""
    eqm = _eqm(model)
    dyn = sw_core._dyn(eqm)
    try:
        v = dyn.EvaluateAll
        if callable(v):
            v = v()
        return bool(v) if v is not None else True
    except Exception as exc:
        raise RuntimeError(f"rebuild_equations 失败: {exc}") from exc


@_pub
def insert_design_table(model, interactive=False):
    """插入设计表（P3，SW 会打开 Excel，交互模式慎用）。

    签名待 SW2018 实测：IModelDoc2::InsertDesignTable(Interactive)。
    """
    dyn = sw_core._dyn(model)
    for args in ((bool(interactive),), ()):
        try:
            ret = dyn.InsertDesignTable(*args)
            return ret
        except Exception as exc:
            if not sw_core.is_arg_count_error(exc):
                raise RuntimeError(f"insert_design_table 失败: {exc}") from exc
    raise RuntimeError("insert_design_table: 所有候选签名失败")


PUBLIC_API = list(_PUBLIC)
