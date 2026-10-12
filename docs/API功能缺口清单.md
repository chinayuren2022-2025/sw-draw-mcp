# SolidWorks 2018 API 功能缺口清单（排除范围之外）

> 本清单用于回答：除“钣金 / 焊件 / 装配爆炸图 / 完整设计表”明确不做外，
> SW2018 API 还有哪些能力是当前插件没有或只做了一部分的。
> 当前插件覆盖：通用零件特征、草图、参考几何/曲线/曲面、多实体、配置/方程式、
> 通用装配配合/组件管理/装配特征，以及读图建模工作流。

## 0. 最近一轮已纳入范围（2026-09-01）

已实现并实机集成测试：

- 装饰螺纹：`sw_features.cosmetic_thread`（InsertCosmeticThread3，实机通过）
- 特征树管理：`rollback_feature` / `rollforward_feature` / `reorder_feature` /
  `rename_feature`（实机通过）；`create_feature_folder` 已封装，但 SW2018
  零件 API 返回 None/False，标记为“不支持，保留清晰报错”
- 尺寸标注：`sw_annotate.py` DimXpert 基础（counts / add_dimension /
  auto_dimension / delete_tolerances，实机通过）
- 渲染：`sw_features.set_appearance`（零件色九元组）+ `set_scene`（场景名，实机通过）
- 装配子装配体：`sw_assembly_full.insert_subassembly` / `find_component` /
  `edit_subassembly`（实机通过）；`dissolve_subassembly` 在简单自建子装配体上
  实机通过（选择对象后 DissolveSubAssembly 返回 True）

半成品验证结论（2026-09-01 实机，后续 2026-09-01 圆角修复）：

- `fillet` 的 variable / face：已修复并实机通过（`docs/reports/fillet_fix_report.json`）
- `fillet` 的 full_round：经多组 Options/选择 mark/API 尝试后仍返回 None，
  维持“需专项验证几何/选择顺序”（IModelDoc2.FeatureFillet3 返回 1 但未落特征树）
- `flex`：InsertFlexFeature 返回 None，维持“参数/选择方式待修复”
- `AddMate4/5`：配合可创建，但返回 error_code=1，lock_rotation 语义未确认，
  维持“基本可用，需复核”

其余条目保留在下方，作为后续可选配置。

## 1. 零件特征层缺口

| 功能 | SW2018 API 参考 | 现状 | 建议优先级 |
|---|---|---|---|
| 模具工具：分型线/分型面/工具分割/关闭曲面/型芯型腔 | `InsertPartingLine` / `InsertPartingSurface` / `InsertToolingSplit` / `InsertShutOffSurface` 族 | ❌ 只有基础 `cavity`/`indent` | P3 |
| Freeform 自由曲面变形 | `IFeatureManager::InsertFreeform` | ❌ 未实现 | P3 |
| 装饰螺纹 | `InsertCosmeticThread` | ❌ 未实现 | P2 |
| 变形 Deform | SW2018 无公开创建签名 | ⚠️ 占位函数 | P3/不做 |
| 弯曲 Flex | `InsertFlexFeature` | ⚠️ 已封装但参数近似、未实机验证 | P3 |
| 异形孔向导高级选项 | `HoleWizard2` 族 | ⚠️ 仅 simple/counterbore/countersink/tapped；未接 Toolbox 标准库、螺纹规格、孔标注 | P2 |
| 全圆角/变半径/面圆角 | `FeatureFillet` 族 | ⚠️ 已封装，但 face/variable/full_round 分支未实机验证 | P2 |
| 特征回滚/编辑定义/重排/重命名 | `EditRollback` / `EditRollForward` / `ReorderFeatures` / `IFeature.Name` | ❌ 只能新建，不能回滚/重排/回读参数再编辑 | P1 |
| 特征树文件夹 | `InsertFeatureTreeFolder2` | ❌ 未实现 | P3 |
| 库特征 | `InsertLibraryFeature` | ❌ 未实现 | P3 |
| 宏特征 | `InsertMacroFeature3` | ❌ 未实现（需注册宏特征） | P3/不做 |

## 2. 草图层缺口

| 功能 | SW2018 API 参考 | 现状 | 建议优先级 |
|---|---|---|---|
| 草图块（制作/插入/爆炸块） | `MakeSketchBlockFromSelected` / `InsertSketchBlockInstance` / `ExplodeSketchBlock` 族 | ❌ 未实现 | P2 |
| 方程式驱动曲线 | `CreateEquationSpline2` | ❌ 未实现 | P2 |
| 圆锥曲线/抛物线 | `CreateConic` / `CreateParabola`（v26 以 TLB 为准） | ❌ 未实现（椭圆已有） | P3 |
| 草图图片 | `InsertSketchPicture` | ❌ 未实现 | P3 |
| 轮廓选择/特征作用域 | `ISelectionMgr::GetSelectedObject6`、FeatureScope | ⚠️ 特征多走 auto-select，未显式暴露轮廓/作用域选择 | P1 |
| 显式完全定义策略 | `FullyDefineSketch` | ⚠️ 只全量 fix，未做“只关系/只尺寸/指定基准”参数化 | P2 |

## 3. 曲面/曲线缺口

| 功能 | SW2018 API 参考 | 现状 | 建议优先级 |
|---|---|---|---|
| 直纹曲面 | `InsertRuledSurfaceFromEdge2` 族 | ❌ 未实现 | P2 |
| 放射曲面 | `InsertRadiateSurface` | ❌ 未实现 | P3 |
| 中间面 | `InsertMidSurface` 族 | ❌ 未实现 | P3 |
| 曲面展平 | `InsertSurfaceFlatten` | ❌ 未实现 | P3 |
| 面部曲线 | `InsertFaceCurve` 族 | ❌ 未实现 | P3 |
| 方程曲线（3D） | `InsertEquationCurve` | ❌ 未实现 | P3 |

## 4. 多实体/实体管理缺口

| 功能 | SW2018 API 参考 | 现状 | 建议优先级 |
|---|---|---|---|
| 保存实体为独立零件 | `IPartDoc::SaveBodies` 族 | ❌ 未实现 | P2 |
| 插入到新零件 | `InsertIntoNewPart` | ❌ 未实现 | P2 |
| 删除/保留实体特征 | `DeleteBody` 特征 | ❌ 未实现（只能删面/布尔） | P1 |
| 实体文件夹/重命名 | Body2.Name | ⚠️ 未暴露 | P3 |

## 5. 零件级管理缺口

| 功能 | SW2018 API 参考 | 现状 | 建议优先级 |
|---|---|---|---|
| DimXpert/MBD 三维标注 | `IDimXpertManager` / `DimXpertAutoDimensionOptions` 族 | ❌ 完全未实现（基准、形位公差、3D 尺寸） | P3 |
| 显示状态 | `IViewDisplayState` / `IModelDocExtension` 显示状态族 | ❌ 未实现（只有配置） | P2 |
| 传感器 | `ISensor` 族 | ❌ 未实现 | P3 |
| 撤销/事务与事件 | `IUndoEvent` / `ISldWorks` 文档事件族 | ❌ 未实现（无事件监听、无回滚事务） | P2 |
| 中性格式导入导出 | `LoadFile4` / `IModelDocExtension::SaveAs2/3`（STEP/IGES/Parasolid/STL/3D PDF） | ❌ 未实现（只保存 SLDPRT/SLDASM） | P1 |
| 视图/显示/渲染控制 | 显示状态、RealView、外观/场景 | ❌ 未实现（只有截图导出） | P3 |

## 6. 装配体缺口

| 功能 | SW2018 API 参考 | 现状 | 建议优先级 |
|---|---|---|---|
| Smart Fasteners/Toolbox 标准件 | `ISmartFastener` 族 | ❌ 未实现 | P3 |
| SpeedPak/大装配模式 | `IAssemblyDoc::SetSpeedPakConfiguration` 族 | ❌ 未实现 | P3 |
| 包络零件、BOM 排除 | `CompConfigProperties4/5` 的 ExcludeFromBOM / IsEnvelope | ❌ 未实现 | P2 |
| 溶解子装配/生成新子装配 | `DissolveSubAssembly` / `FormNewSubAssembly` | ❌ 未实现 | P2 |
| 装配配置/显示状态/零部件属性 | `IAssemblyDoc.AddConfiguration2` / `IComponent2.SetReferencedDisplayStates` | ❌ 未实现 | P2 |
| 配合类型完整实测 | `AddMate3/4/5` | ⚠️ 已封装全部类型与参数，但 4/5 回退与多数 mate type 未实机验证 | P1 |
| 运动算例 | `IMotionStudy` 族 | ❌ 未实现（不在几何建模范围） | P3/不做 |
| 爆炸视图 | `ConfigurationManager.AddExplodeStep` 族 | ❌ 按约定不做 | 不做 |
| 焊件/钣金 | 相关 API 族 | ❌ 按约定不做 | 不做 |

## 7. 工程图/文档层（完整说明）

插件定位是“零件/装配建模 + 读图”，以下 SW API 完全未实现（如需要属于新的大模块）：

- 工程图创建：图纸模板、三视图/剖视图/局部视图、尺寸/公差/注解/BOM 表格。
- 3D PDF、eDrawings 发布。
- 文档管理（PDM add-in、Pack and Go）。

## 8. 建议的下一批 P1（如果要继续扩）

1. 特征回滚/重排/编辑 + 特征作用域显式选择
2. 删除/保留实体、保存实体、插入到新零件
3. 中性格式导入导出（STEP/IGES/STL）
4. 配合 4/5 回退与未实测 mate type 的实机验证
5. 草图块与方程式驱动曲线
