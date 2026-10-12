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

## 注意事项

- 建模前尽量先调用 dry-run 或 spec 校验。
- 建模后调用 `part_inspect` / `sketch_check`。
- `drawing_compare` 默认不启用 OpenCV；如需要深度 CV，传 `use_cv=true`。
- 不要使用 WSL UNC 路径，使用 `D:\...` 绝对路径。
