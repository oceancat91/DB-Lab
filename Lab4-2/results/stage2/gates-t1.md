# 二阶段门禁记录：题目实体与版本数据模型

日期：2026-10-22，Asia/Shanghai。结论基于本次实际执行，未运行项已注明。

## G1.1

五个新集合（questions、question_versions、question_shares、question_banks、question_bank_items）的字段、索引与访问模式已说明；题目内容只在不可变版本中保存，问卷草稿与发布快照保留副本并用 question_version 指向版本。

证据：../docs/DATABASE.md

## G1.2

在真实 MongoDB 副本集上建立集合、strict/error 校验与全部索引，非法文档与重复版本被数据库拒绝。

证据：schema-check.json
