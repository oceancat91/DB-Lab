# 二阶段门禁记录：题目库页面与流程

日期：2026-10-22，Asia/Shanghai。结论基于本次实际执行，未运行项已注明。

## G3.1

新增 /library 页面：题目列表（我的/共享给我）、新建题目、详情、版本历史、恢复、共享、题库、加入问卷、跨问卷统计；样式复用一阶段设计令牌，未改动一阶段 app.js。

证据：http-e2e.json 与 ../docs/SYSTEM.md

## G3.2

用 Chrome DevTools Protocol 驱动真实 Chrome 跑通登录后主流程：页面内注册与登录、打开 /library、填写并提交新建题目表单、列表出现、点开详情与版本历史、打开跨问卷统计面板，7/7 步通过且无未捕获脚本异常；截图与 report.json 见 results/stage2/browser/。未点击的部分：恢复按钮、共享表单、题库更新版本、加入问卷下拉。

证据：gates-t3.md 下文
