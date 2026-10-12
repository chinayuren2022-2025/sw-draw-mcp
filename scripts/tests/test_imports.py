"""import 级冒烟测试：用测试桩导入全部新模块，校验 PUBLIC_API 完整且函数可解析。

在 Windows 上同样可跑（测试桩优先，不影响真实 pywin32 安装）。
"""
import inspect
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
STUBS = os.path.join(HERE, "stubs")
sys.path.insert(0, STUBS)
sys.path.insert(0, SCRIPTS)


class TestImports(unittest.TestCase):
    def _load(self, name):
        import importlib
        return importlib.import_module(name)

    def test_core_imports(self):
        import sw_core
        import sw_sel
        import sw_sketch
        import sw_features
        import sw_advanced
        import sw_check
        import sw_config
        import sw_assembly_full
        import sw_annotate
        import sw_part_dsl
        for mod in (sw_core, sw_sel, sw_sketch, sw_features, sw_advanced, sw_check,
                    sw_config, sw_assembly_full, sw_annotate):
            self.assertTrue(hasattr(mod, "__name__"))

    def test_public_api_resolves(self):
        import sw_sketch
        import sw_features
        import sw_advanced
        import sw_config
        import sw_assembly_full
        for mod in (sw_sketch, sw_features, sw_advanced, sw_config,
                    sw_assembly_full):
            names = getattr(mod, "PUBLIC_API", None)
            self.assertIsInstance(names, list, mod.__name__)
            self.assertTrue(names, mod.__name__)
            for name in names:
                fn = getattr(mod, name)
                self.assertTrue(callable(fn), f"{mod.__name__}.{name}")
                inspect.signature(fn)  # 至少可解析（无 model 的辅助函数允许存在）

    def test_dsl_contracts(self):
        import sw_part_dsl
        import sw_sketch
        import sw_features
        import sw_advanced
        import sw_config
        import sw_annotate
        mods = {"sw_sketch": sw_sketch, "sw_features": sw_features,
                "sw_advanced": sw_advanced, "sw_config": sw_config,
                "sw_annotate": sw_annotate}
        for op, (mod_name, fn_name, mapping) in sw_part_dsl._FEATURE_OPS.items():
            fn = getattr(mods[mod_name], fn_name)
            params = inspect.signature(fn).parameters
            for target in mapping.values():
                self.assertIn(target, params, f"{op}: {fn_name} 缺参数 {target}")
        for etype in sw_part_dsl._SKETCH_ENTITY_PARAMS:
            fn = getattr(sw_sketch, etype)
            params = inspect.signature(fn).parameters
            for p in sw_part_dsl._SKETCH_ENTITY_PARAMS[etype]:
                self.assertIn(p, params, f"entity {etype}: 缺参数 {p}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
