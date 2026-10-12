# MCP 工具速查表

> 所有尺寸单位默认毫米（mm）；输出文件默认在 `SW_DRAW_OUTPUT` 或 `output/`。

| 工具 | 用途 | 关键参数 | 示例 |
|---|---|---|---|
| `sw_status` | 检查 SW 连接/版本 | 无 | `{}` |
| `lens_dry_run` | 透镜参数预览 | D, f, material | `{"D":25,"f":50,"material":"BK7"}` |
| `lens_build` | 平凸透镜建模 | D, f, material | `{"D":25,"f":50,"material":"BK7"}` |
| `barrel_build` | 镜筒建模 | params | 见 README |
| `assemble` | 两件套自动装配 | insert, into, save | `{"insert":"a.SLDPRT","into":"b.SLDPRT"}` |
| `sketch_check` | 草图约束检查 | file, fix | `{"file":"out.SLDPRT","fix":false}` |
| `part_spec_dry_run` | 通用零件 spec 预检 | spec | 见 examples |
| `part_build` | 通用零件建模 | spec, out | 见 examples |
| `feature_create` | 单特征创建 | file, feature | `{"feature":{"op":"fillet","radius_mm":2}}` |
| `ref_geometry_create` | 参考几何 | file, spec | `{"spec":{"op":"ref_plane","plane_type":"offset"}}` |
| `sketch_create` | 创建独立草图 | file, plane, entities | `{"plane":"front","entities":[...]}` |
| `part_inspect` | 零件深度检查 | file | `{"file":"out.SLDPRT"}` |
| `assembly_spec_dry_run` | 装配 spec 预检 | spec | 见 examples |
| `assembly_build` | 通用装配建模 | spec, out | 见 examples |
| `drawing_ingest` | 工程图解析 | input, out_dir | `{"input":"D:\\drawing.pdf"}` |
| `drawing_build` | 按 drawing_spec 建模 | spec, out | 见 examples/mm25 |
| `drawing_compare` | 模型/图纸对比 | drawing_json, model_views_dir | `{"drawing_json":"...","model_views_dir":"..."}` |
| `annotation_create` | DimXpert 尺寸标注 | op, dim_type, face_spec | `{"op":"dimxpert_add_dimension","dim_type":"size"}` |
| `subassembly_manage` | 子装配体管理 | op, comp, path | `{"op":"insert","path":"sub.SLDASM"}` |

## v2：闭环工具（看 → 稳定引用 → 操作 → 验证）

`file` 参数统一可为：路径（自动打开）、已打开文档标题、或空 = 活动文档。

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `doc_list` / `doc_open` / `doc_save` / `doc_close` | 文档管理 | path, file, save |
| `doc_export` | 按扩展名导出 STEP/IGES/STL/x_t/PDF/DXF/eDrawings | path |
| `view_capture` | 标准视角截图，**直接返回图片**供 AI 目视检查 | view (front/top/isometric/...), width, height |
| `feature_list` | 特征树（类型、压缩、错误码、子特征） | include_sub |
| `feature_suppress` / `feature_delete` / `undo` | 可逆排查 / 删除（返回级联删除清单）/ 撤销 | name, count |
| `dimension_list` / `dimension_set` | 尺寸全名与值（mm/deg），按全名改并重建 | name, value |
| `custom_properties` | 读/写自定义属性 | props, config |
| `part_topology` | 面/边：类型、法向/轴/半径、面积、包围盒、名字、persist_id | kind, include_edges |
| `entity_name` | 给零件面/边命名（存进零件），装配中按名引用 | ref, name |
| `measure` | 距离/法向距离/角度/半径/面积/平行/垂直（零件或装配） | ref1, ref2 |
| `mass_properties` | 体积/质量/质心/包围盒 | file |
| `asm_new` / `asm_insert` | 新建装配 / 插入组件（`place="origin"` 让零件原点精确落位） | path, at_mm, fix |
| `asm_components` / `asm_component_faces` | 组件状态、剩余自由度、变换；组件的面（装配坐标） | component, kind |
| `asm_mate` | 闭环配合：返回两端约束状态与剩余自由度，冲突自动回滚 | a, b, mate_type, align, distance_mm |
| `asm_mates` / `asm_mate_edit` / `asm_mate_delete` / `asm_mate_suppress` | 读回 / 改值或翻转 / 删除 / 压缩配合 | name |
| `asm_move` / `asm_fix` | 平移组件 / 固定或浮动 | component, delta_mm, to_mm |
| `asm_check` | 配合错误、欠定义(floating)、过定义、干涉、What's Wrong | interference |

### 引用写法（`entity_name` / `measure` / `asm_mate`）

```jsonc
// 零件内
{"name": "HOLE"}                                   // 已命名实体（最稳）
{"persist_id": "<base64>"}                         // part_topology 返回，重建后仍有效
{"spec": {"kind": "cylinder", "radius_mm": 5}}     // 几何过滤
{"ray": {"origin_mm": [0,0,50], "direction": [0,0,-1]}}
// 装配内
{"component": "pin-1", "face": "PIN_CYL"}          // 组件 + 零件中的面名
{"component": "pin-1", "plane": "right"}           // 组件基准面
{"component": "pin-1", "axis": "基准轴1"} / {"component": "pin-1", "point": "origin"}
{"plane": "front"}                                 // 装配体自身基准面
```

### 推荐工作流

```
零件：part_build（spec 里用 "names" 直接给配合面命名）→ part_topology → view_capture
      → dimension_list / dimension_set
装配：asm_new → asm_insert → asm_mate（组件+面名）→ 看 status / remaining_dofs
      → asm_check → view_capture
```

## 注意事项

- 建模前尽量先调用 dry-run 或 spec 校验。
- 建模后调用 `part_inspect` / `sketch_check`。
- `drawing_compare` 默认不启用 OpenCV；如需要深度 CV，传 `use_cv=true`。
- 不要使用 WSL UNC 路径，使用 `D:\...` 绝对路径。
