# S7 时点打包产物快照

本目录保存 S7 通过时点的打包证据副本，用于把「S7 基线」与「S7 之后用户授权的界面改版」分开留痕。这里的文件都是**逐字节副本**，没有修改原文件。

## 为什么会有这个目录

S7 通过后，用户要求在 Lab4 内优化问卷填写页面。该改动只涉及表现层，但会改变提交包与基线摘要，因此：

- 原 `results/S7/manifest.json`、`results/S7/package-check.json` 按 S7 时点内容复制到本目录；
- 原 `dist/Lab4-stage1.zip` 复制为 `dist/Lab4-stage1-s7-baseline.zip`（含 `.zip.sha256`）；
- 交付包 `dist/Lab4-stage1.zip` 随后由当前工作树重建，其摘要记录在新的 `results/S7/manifest.json` 与 `dist/Lab4-stage1.zip.sha256` 中。

## 快照清单与摘要

| 快照 | 来源 | 字节 | SHA-256 |
| --- | --- | --- | --- |
| `manifest-s7-baseline.json` | `results/S7/manifest.json`（S7 时点） | 27732 | `a2b7fbf242e894ccedc68482f98f3b67045afffd6e54a682f646da3984290950` |
| `package-check-s7-baseline.json` | `results/S7/package-check.json`（S7 时点） | 634 | `ab66f80278fe405c27be88dd4a28329de1e4e5f6ce72a7086f9fda21d81dcd6d` |
| `dist/Lab4-stage1-s7-baseline.zip` | `dist/Lab4-stage1.zip`（S7 时点，dist 目录不在提交包内） | 636693 | `1dd92dcb5dac605183db384c7b91c529fc3acd219727ced0b43771ca8989ba5f` |

S7 时点交付包对应代码提交 `e7255c3332b3492691eff27a0a5ce7e395127422`，可从 Git 历史重建。

## 改版影响的文件范围（实测）

以 `results/S7/code-baseline.json` 的 21 个业务文件逐项重算摘要：19 项与 S7 基线一致，2 项改变，0 项缺失。改变的只有表现层文件 `survey_app/static/app.css` 与 `survey_app/static/app.js`；服务端、Schema、校验、跳转、提交、统计与全部测试文件均未改动。逐项结果见 [基线复核](../../ui-refresh/code-baseline-check.json)。

## 结论范围

- S7 门禁 G7.1–G7.3 的实质结论不变：可运行代码、Schema、配置说明、设计文档、测试用例与真实结果齐备；改版后全量 245 项测试再次通过（`results/local-run.json`），并补充了真实浏览器验证（[改版证据](../../ui-refresh/review.md)）。
- 本目录不改变任何原有验收断言，也不替代 S7 时点的原始记录；原文件仍保留在 `results/S7/` 与 `dist/` 原路径。
- 改版经过、设计判断与未验证范围见实验日志 EXP-013 条目。
