# 工程图读图规则（drawing workflow 知识库）

本文件用于沉淀“读工程图→建模”时容易踩的坑，供 LLM/规则引擎共同使用。

## 1. 先看投影角

- 标题栏常见 `THIRD ANGLE PROJECTION`（第三角）或 `FIRST ANGLE PROJECTION`（第一角）。
- 第三角投影下：
  - 主视图（Front）在左上/左上主位
  - 俯视图（Top）在主视图上方或下方？依据标准规范；从 mm25 的实际布局看：
    - 上方矩形带单孔 = Top/Front 面
    - 下方长圆带双孔 = Front 视图
- 不确定时，用“视图间尺寸长对正、高平齐、宽相等”做回溯验证。

## 2. 视图到 SW 基准面映射（推荐）

- 工程图 Front 视图 → SW Front Plane（XY）
- 工程图 Top 视图 → SW Top Plane（XZ，即 Y 向观察）
- 工程图 Right 视图 → SW Right Plane（YZ，即 X 向观察）
- 拉伸方向：垂直于所对应基准面。

## 3. 通孔 vs 盲腔

- 一个视图中是圆，另一个视图中出现矩形/隐藏线 → 通常是贯通孔。
- 一个封闭轮廓内部不是背景白，而是零件色/黄色/灰色底面 → 通常是盲腔或凹槽，**不能直接做成贯通切除**。
- 剖视图（Section A-A / B-B）上的缺口、壁厚、`20`/`10` 等尺寸是判断深度和是否贯通的权威依据。

## 4. 圆角/倒角

- `TYP`、`ALL RED FILLETS`、`R2 TYP` 等注记表示多个边统一圆角，必须是**必建特征**，不能当成“可选项”。
- 建模后如果在某个视图发现缺失圆角，应回补，不能直接交付。

## 5. 剖面线

- 剖面线（hatching）区域 = 被切割的材料。
- 非剖面线、但有颜色的区域通常是腔体底面/内表面。
- 靠剖面线区分“实体保留”和“已被切除”。

## 6. 对称特征

- 图纸左右/前后对称时，优先用镜像、线性/圆周阵列，不要手工重复画。
- 镜像平面可用中间基准面（Offset Plane），镜像后如有显示基准面，可在截图时隐藏，不影响零件。

## 7. SW 视图与截图坑

- 中文 SolidWorks 中标准视图名是 `*前视`、`*上视`、`*等轴测` 等。
- `IModelDoc2.ShowNamedView(name)` 可用；`ShowNamedView2(name, 1)` 在 SW2018 中文版里疑似失效，应优先使用 `ShowNamedView`。
- `model.SaveBMP(path, 0, 0)` 可以导出当前视图位图。
- 参考基准面显示开关：`ViewDispRefplanes()`、`ViewDispOrigins()`、`ViewDispRefPoints()`、`ViewDispTempRefaxes()` 是无参 toggle 方法（调用一次切换显示状态）。

## 8. 读图流程强约束

1. 先输出视图清单（Front/Top/Right/Section）。
2. 再输出每个视图的几何假设。
3. 再输出特征假设表（含置信度与证据）。
4. 建模前必须把 `TYP` 圆角、`THRU` 贯通、盲腔深度写进 spec。
5. 建模后必须回拍并对比，`needs_review` 时不允许直接声称完成。
