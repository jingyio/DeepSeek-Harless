本轮是隔离的 RSI 工具学习，不是论文事实核验。请用 Harness 原生 Cordis 工作流自己编写、运行、测试和修复一个可复用的报告结构检查工具。禁止读写文件、联网、启动子 Agent 或生成任意 JS 检查算法；检查算法写成下述有界纯数据程序。动态包只作为提交包装。

契约：candidate = {schema_version:1,name:"check_report_structure",description:"中文说明",program:<表达式>}。
输入变量 input = {report:{scope,citation_issues,references:[{key,arxiv_id,...}]},expected_pairs:[[key,id],...],current_source_version,expected_source_version}。
输出必须恰好包含 missing_pairs、unexpected_pairs、duplicate_pairs（都是去重后的 [key,id] 数组，按输入首次出现顺序），以及 source_mismatch、scope_mismatch、malformed（三个 boolean）。
missing_pairs 为期望中不在报告里的配对；unexpected_pairs 为报告中不在期望里的配对；duplicate_pairs 为报告内重复出现的配对。
scope 必须是 cited_arxiv_version_triage。malformed 表示 report 非 object、references 非 array，或任何条目非 object / key 或 arxiv_id 非 string；排除这些无效条目后仍检查合法条目的覆盖。空 references 对空 expected_pairs 合法。source_mismatch 比较当前来源版本与期望来源版本，版本从调用方取得，不信任报告自报版本。不判定真实性、DOI、年份、版本选择或文字质量。

所有表达式是数组 [op,...args]：
- ["lit",JSON值] 字面量；["var","input"] 输入；["var",变量名] 绑定。
- ["get",表达式,字段名表达式] 只取自身字段/数组索引，缺失返回 null；禁止 constructor/prototype/__proto__。
- ["let",变量名,值表达式,主体表达式]；["if",条件,真分支,假分支]，仅求值选中的分支。
- ["object",{字段名:表达式,...}]；["array",表达式,...]。
- ["map",数组表达式,变量名,主体]；["filter",数组表达式,变量名,谓词]。
- ["unique",数组] 去重；["difference",数组1,数组2] 返回数组1中不在数组2的元素，保持顺序（需要另行 unique）；["concat",数组,...]；["count",数组]。
- ["eq",值1,值2] JSON 深比较；["not",条件]；["and",条件,...]；["or",条件,...]；["gt",数1,数2]。
- ["type",表达式] 返回 object/array/string/number/boolean/null；["join",字符串数组,分隔符]。
变量名只用字母数字下划线，不执行宿主函数。限制1500节点、40层、200000运算、2000数组元素、192KB输入输出。不要把样例的 key、id、source_version 写死。

隔离进程提供 ctx.get('sssPaperRsi').install(candidate)。先通过 cordis_inspect_list / cordis_inspect_query 核对可用宿主接口，再用 cordis_define 创建纯 host 包，其 code.host 形如 `return {apply(ctx){ ctx.get('sssPaperRsi').install(candidate); }};`，candidate 由你完整生成，不要使用 client 半。
用 cordis_run 激活；随后运行 rsi_test 查看开发样例。失败时定义同一插件的新版本并 update，直到开发样例通过。再调用 rsi_trial，传入下面一个开发样例的 input，确认生成工具真实可调用。最后只报告是否完成及候选摘要，不声称独立认证或节省成本。

开发样例（不包含独立验收样例）：
{{TRAINING}}
