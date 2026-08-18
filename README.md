# Project Graph Architect

这是一个面向 Project Graph `.prg` 生成的可移植 Skill 包。

## 默认能力
- 从自然语言项目 / 思路提取图模型
- 选择 Project Graph 原生原语
- PRG 2.7.0 序列化
- 关系感知布局
- 主题安全配色
- 结构校验
- 近似几何冲突审计

## 快速测试

```bash
python -m pip install -r requirements.txt
python examples/minimal_example.py
python scripts/validate_prg.py examples/minimal_project_graph.prg
python scripts/layout_audit.py examples/minimal_project_graph.prg
```

## 许可与声明

本项目采用 GPL-3.0-only。它是非官方社区项目，与 Project Graph、Graphif
及其维护者不存在隶属、背书或赞助关系。详情见 `LICENSE` 与 `NOTICE.md`。

## 设计准则
最重要的两个原则：

> 先分区，后摆点；先留白，后连线；先语义，后装饰；先可读，后紧凑。

> 不是“块之间不重叠”就够了，而是块、线、标签、群组边界都必须拥有安全活动空间。
