# Agent 常用任务模板

## 1. 画平凸透镜

```text
1. lens_dry_run({"D":25,"f":50,"material":"BK7"})
2. lens_build({"D":25,"f":50,"material":"BK7"})
3. 返回输出路径
```

## 2. 按工程图建模

```text
1. drawing_ingest({"input":"D:\\drawings\\mm25-p1-1.pdf"})
2. drawing_build(spec, out="D:\\sw-draw-skill\\output\\mm25_p1_1.SLDPRT")
3. capture_model_views()
4. drawing_compare(drawing_json, model_views_dir)
5. 返回模型路径
```

## 3. 装配两个零件

```text
1. assembly_spec_dry_run(spec)
2. assembly_build(spec, out="D:\\sw-draw-skill\\output\\asm.SLDASM")
```

## 4. 给当前零件加装饰螺纹

```text
feature_create({
  "file": "D:\\sw-draw-skill\\output\\part.SLDPRT",
  "feature": {
    "op": "cosmetic_thread",
    "edge_spec": {"kind":"edge","type":"circle","radius_mm":5},
    "diameter_mm": 10,
    "depth_mm": 10,
    "end_condition": "blind",
    "note": "M10"
  }
})
```

## 5. 给当前零件加 DimXpert 尺寸

```text
annotation_create({
  "file": "D:\\sw-draw-skill\\output\\part.SLDPRT",
  "op": "dimxpert_add_dimension",
  "dim_type": "size",
  "face_spec": {"kind":"cylinder","radius_mm":5}
})
```

## 6. 子装配体管理

```text
subassembly_manage({
  "file": "D:\\sw-draw-skill\\output\\top.SLDASM",
  "op": "insert",
  "path": "D:\\sw-draw-skill\\output\\sub.SLDASM"
})
```

## 7. 检查模型

```text
part_inspect({"file":"D:\\sw-draw-skill\\output\\part.SLDPRT"})
sketch_check({"file":"D:\\sw-draw-skill\\output\\part.SLDPRT"})
```
