# mm25-p1-1 回归案例

- 源图：`/home/zjulin/ai+sw/mm25-p1-1.pdf`
- 解析结果：`../../output/drawing/mm25/drawing.json`
- 视图理解：`../../output/drawing/mm25/interpretation.json`
- 建模 spec：`drawing_spec.json`
- 模型：`../../output/mm25_p1_1.SLDPRT`
- 回拍视图：`../../output/views/`
- 比对结果：`../../output/drawing/mm25/compare.json` + `compare_front/top/isometric.png`

运行：

```bash
# 解析
python scripts/drawing_ingest.py /home/zjulin/ai+sw/mm25-p1-1.pdf \
  --out-dir output/drawing/mm25
# 视图理解
python scripts/drawing_interpret.py output/drawing/mm25/drawing.json
# 建模（Windows SW 端）
D:\\FastProgram\\python\\python.exe scripts/drawing_spec.py examples/mm25/drawing_spec.json
# 回拍
python scripts/capture_model_views.py
# 对比
python scripts/model_view_compare.py output/drawing/mm25/drawing.json output/views
```
