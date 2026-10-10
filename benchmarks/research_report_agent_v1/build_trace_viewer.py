"""Build an offline Chinese viewer from actual benchmark records only.

Example:
  python build_trace_viewer.py --runs-root .local/research-report-agent \
    --library .local/research-report-agent/library.json --output .local/viewer/index.html

No model calls, no generated/fabricated trace events, no external assets/fetch.
The resulting HTML contains private raw requests; keep it outside version control.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote


def load_json(path, default=None):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return {"_viewer_read_error": type(exc).__name__, "path": str(path)}


def load_jsonl(path):
    if not path.is_file():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append({"_viewer_read_error": "invalid_json_line", "line": number})
    return rows


def redact(value):
    """Defensive rendering boundary; execution records remain unchanged."""
    if isinstance(value, str):
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED_API_KEY]", value)
        return re.sub(r"(?i)(authorization\s*[:=]\s*['\"]?bearer\s+)[^\s,'\"}]+", r"\1[REDACTED]", value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in {"api_key", "apikey", "authorization", "access_token"}
                else redact(item) for key, item in value.items()}
    return value


def observation(event):
    data = event.get("data", {})
    blocks = data.get("message", {}).get("content", [])
    error = bool(data.get("error"))
    parsed = None
    texts = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        error = error or block.get("isError") is True
        for item in block.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                texts.append(text)
                try:
                    value = json.loads(text)
                    if isinstance(value, dict):
                        parsed = value
                except ValueError:
                    pass
    if isinstance(parsed, dict):
        error = error or any(parsed.get(field) is False for field in ("ok", "passed", "quality_passed"))
    return parsed, error, texts


def response_summary(text):
    """Join actual streaming tool call fragments; do not infer model actions."""
    chunks = []
    if text.lstrip().startswith("{"):
        try:
            chunks = [json.loads(text)]
        except ValueError:
            pass
    else:
        for line in text.splitlines():
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                try:
                    chunks.append(json.loads(line[5:].strip()))
                except ValueError:
                    continue
    calls, content, usage = {}, [], None
    for chunk in chunks:
        if isinstance(chunk.get("usage"), dict):
            usage = chunk["usage"]
        for choice in chunk.get("choices", []):
            delta = choice.get("delta") or choice.get("message") or {}
            if isinstance(delta.get("content"), str):
                content.append(delta["content"])
            for tool in delta.get("tool_calls", []):
                index = tool.get("index", len(calls) if "message" in choice else 0)
                found = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if tool.get("id"):
                    found["id"] = tool["id"]
                function = tool.get("function", {})
                if function.get("name"):
                    found["name"] += function["name"]
                found["arguments"] += function.get("arguments", "")
    return {"tool_calls": list(calls.values()), "text": "".join(content), "usage": usage}


def artifact_links(run, output):
    workspace = run / "workspace"
    found = []
    if not workspace.is_dir():
        return found
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".pdf", ".png", ".svg", ".docx"}:
            relative = os.path.relpath(path.resolve(), output.parent.resolve()).replace(os.sep, "/")
            found.append({"name": path.name, "path": str(path.relative_to(run)),
                          "href": quote(relative, safe="/._-"), "kind": path.suffix.lower()[1:],
                          "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return found


def collect_run(path, manifest, output):
    metrics = load_json(path / "metrics.json", {})
    events = load_jsonl(path / "agent-events.jsonl")
    audits = load_jsonl(path / "motif-audit.jsonl")
    ledger = load_jsonl(path / "cost-ledger.jsonl")
    request_rows, model_origin = [], {}
    costs = {row.get("request_id"): row for row in ledger}
    for request_path in sorted((path / "model-requests").glob("*.request.json")):
        request_id = request_path.name.removesuffix(".request.json")
        response_path = request_path.with_name(request_id + ".response.txt")
        raw_response = response_path.read_text(encoding="utf-8", errors="replace") if response_path.is_file() else None
        parsed = response_summary(raw_response or "")
        number = len(request_rows) + 1
        for call in parsed["tool_calls"]:
            if call["id"]:
                model_origin[call["id"]] = number
        request_rows.append({"number": number, "request_id": request_id,
                             "request": load_json(request_path), "response_raw": raw_response,
                             "response": parsed, "cost": costs.get(request_id)})
    motif_origin = {row["call_id"]: row for row in audits
                    if row.get("kind") == "motif_bypass_attempt" and row.get("call_id")}
    verified = {row.get("call_id") for row in audits if row.get("kind") == "model_request_skipped_verified"}
    tools, by_call, loop = [], {}, 0
    for event in events:
        data = event.get("data", {})
        if event.get("type") == "step/start":
            loop += 1
        if event.get("type") == "tool/call":
            call_id = data.get("callId")
            arguments = data.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    pass
            row = {"number": len(tools) + 1, "loop": loop, "call_id": call_id,
                   "tool": data.get("name"), "arguments": arguments, "call_event": event,
                   "result_events": [], "output": None, "error": False, "result_text": [],
                   "origin": "motif" if call_id in motif_origin else "llm",
                   "model_request": model_origin.get(call_id), "motif": motif_origin.get(call_id),
                   "verified_bypass": call_id in verified}
            tools.append(row); by_call[call_id] = row
        elif event.get("type") == "tool/result":
            call_id = data.get("message", {}).get("source", {}).get("callId")
            row = by_call.get(call_id)
            if row:
                row["result_events"].append(event)
                operation = event.get("surfaceOp")
                if operation is None or operation == "append" or (isinstance(operation, dict) and operation.get("op") == "append"):
                    value, failed, texts = observation(event)
                    row.update(output=value, error=failed, result_text=texts)
    answer = (path / "answer.md").read_text(encoding="utf-8") if (path / "answer.md").is_file() else None
    return {"directory": path.name, "path": str(path), "manifest": manifest, "metrics": metrics,
            "tools": tools, "requests": request_rows, "audits": audits, "ledger": ledger,
            "answer": answer, "artifacts": artifact_links(path, output),
            "diagnostics": load_json(path / "error-diagnostics.json"),
            "event_count": len(events), "observed_loop_steps": loop,
            "raw_events": events}


def build(runs_root, library_path, output):
    runs = []
    for manifest_path in sorted(runs_root.rglob("manifest.json")):
        manifest = load_json(manifest_path, {})
        if not isinstance(manifest, dict) or "case_id" not in manifest or "mode" not in manifest:
            continue
        runs.append(collect_run(manifest_path.parent, manifest, output))
    library = load_json(library_path) if library_path else None
    payload = redact({"built_utc": datetime.now(timezone.utc).isoformat(), "runs_root": str(runs_root),
                      "library": library, "runs": runs})
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    serialized = serialized.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(HTML.replace("__EMBEDDED_DATA__", serialized), encoding="utf-8")
    return {"output": str(output), "runs": len(runs), "tool_calls": sum(len(run["tools"]) for run in runs),
            "recorded_model_requests": sum(len(run["requests"]) for run in runs), "bytes": output.stat().st_size}


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self' data: file:; font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>科研报告 Agent · 真实执行记录</title><style>
:root{--ink:#19303b;--muted:#667982;--line:#dce4e5;--paper:#fff;--bg:#f3f5f3;--teal:#087b6c;--blue:#275ba8;--violet:#7052a6;--bad:#a42d31;--warm:#ba7628}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 'Segoe UI','Microsoft YaHei',sans-serif}header{background:#142f3c;color:#fff;padding:35px max(28px,calc((100vw - 1300px)/2));border-bottom:5px solid #56b7a6}.eyebrow{font:12px/1.5 monospace;letter-spacing:2px;color:#a8d6cc}h1{font-size:29px;line-height:1.4;font-weight:650;margin:9px 0}header p{margin:0;max-width:950px;color:#cbdade}.shell{max-width:1356px;margin:auto;padding:25px 28px 70px}h2{font-size:22px;margin:0 0 15px}h3{font-size:16px;margin:0 0 7px}p{margin:8px 0}a{color:var(--blue)}button,select,input{font:inherit}select{background:white;padding:10px 12px;border:1px solid #b9c8cd;border-radius:8px;max-width:100%;min-width:290px;color:var(--ink)}.toolbar{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:20px}.toolbar label{font-weight:650}.muted{color:var(--muted);font-size:13px}.tabs{display:flex;gap:8px;border-bottom:1px solid var(--line);padding-bottom:10px;margin:24px 0 22px;flex-wrap:wrap}.tabs button{padding:9px 17px;border:1px solid transparent;border-radius:7px;background:transparent;cursor:pointer;color:var(--muted)}.tabs button[aria-selected=true]{color:white;background:var(--ink)}.tabs button:hover{border-color:#adbcbf}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:18px}.card{background:var(--paper);border:1px solid var(--line);padding:16px;border-radius:9px}.card b{font-size:27px;line-height:1.2;display:block;font-variant-numeric:tabular-nums}.card span{font-size:12px;color:var(--muted)}.pill{display:inline-block;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600;background:#edf0f2;color:#445b68;margin-right:5px}.llm{background:#e7effd;color:var(--blue)}.motif{background:#ddf3ec;color:var(--teal)}.mcp{background:#eee8f8;color:var(--violet)}.bad{background:#ffeaeb;color:var(--bad)}.ok{background:#ddf3ec;color:var(--teal)}.warn{background:#fff1d9;color:#93611f}.call{border:1px solid var(--line);background:white;border-radius:10px;margin-bottom:14px;overflow:hidden}.call.motif-border{border-left:4px solid var(--teal)}.call.llm-border{border-left:4px solid var(--blue)}.calltop{padding:16px 19px;display:flex;justify-content:space-between;align-items:flex-start;gap:18px;background:#fafcfb;border-bottom:1px solid #edf0f0}.calltop h3{font-size:16px;font-family:Consolas,monospace;word-break:break-word}.callbody{padding:14px 19px}.columns{display:grid;grid-template-columns:1fr 1.2fr;gap:18px}.label{font-size:12px;font-weight:700;letter-spacing:.4px;color:var(--muted);margin-bottom:7px}.snippet{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.65 Consolas,monospace;background:#f3f6f6;padding:12px;border-radius:6px;max-height:220px;overflow:auto;margin:0}.kv{margin:0}.kv div{display:grid;grid-template-columns:155px 1fr;border-bottom:1px solid #edf1f1;gap:10px;padding:5px 0;font-size:12px;overflow-wrap:anywhere}.kv dt{color:var(--muted)}.kv dd{margin:0;font-family:Consolas,monospace}details{margin-top:10px}summary{cursor:pointer;font-size:13px;color:var(--blue);padding:3px 0}pre.raw{white-space:pre-wrap;overflow-wrap:anywhere;max-height:520px;overflow:auto;background:#132d38;color:#e2eeed;border-radius:7px;padding:17px;font:12px/1.7 Consolas,monospace}.note{border-left:3px solid #92b7b0;padding:13px 17px;background:#eaf2ef;border-radius:0 6px 6px 0;margin:16px 0}.note.warning{border-color:#c39558;background:#fff4e2}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.flow{position:relative;padding:22px;border:1px solid var(--line);background:white;border-radius:10px}.flow b{font-size:19px}.flow .step{padding:9px 11px;border-radius:6px;margin-top:10px;font-size:13px}.flow .arrow{padding:1px 11px;color:#8aa3a4}.flow:not(:last-child):after{content:'→';position:absolute;right:-14px;top:47%;z-index:1;background:var(--bg);font-size:21px;color:#648389}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.box{border:1px solid var(--line);background:white;border-radius:9px;padding:21px;margin-bottom:18px}.empty{border:1px dashed #b8c8cc;border-radius:8px;padding:30px;color:var(--muted)}.filters{display:flex;gap:15px;align-items:center;margin-bottom:16px;flex-wrap:wrap}.filters input[type=search]{padding:8px 11px;border:1px solid #bdcccf;border-radius:6px;min-width:270px;background:white}.edge{display:grid;grid-template-columns:1fr auto 1fr;gap:18px;align-items:center;font:14px/1.7 Consolas,monospace;padding:15px;background:#f1f6f3;border-radius:7px;overflow-wrap:anywhere}.edge small{font:12px 'Segoe UI','Microsoft YaHei',sans-serif;color:var(--muted);display:block}.witness{font-size:13px;border-top:1px solid var(--line);padding-top:11px;margin-top:13px}.assetlist{display:flex;flex-wrap:wrap;gap:9px}.assetlist a{padding:8px 12px;border:1px solid var(--line);border-radius:7px;background:white;font-size:13px;text-decoration:none}.statusline{font-size:13px;line-height:1.7;margin-bottom:17px;color:var(--muted);overflow-wrap:anywhere}.modelcontent{white-space:pre-wrap;background:#f4f7fb;padding:13px;border-radius:6px;font-size:14px;max-height:250px;overflow:auto}.legend{display:flex;gap:15px;flex-wrap:wrap;font-size:13px;margin-bottom:16px}.progress{height:6px;background:#dce7e6;border-radius:10px;overflow:hidden;margin:14px 0}.progress i{display:block;background:var(--teal);height:100%}footer{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:16px;margin-top:25px}code{font:12px Consolas,monospace;background:#edf2f1;padding:1px 4px;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid var(--line);text-align:left;padding:10px 12px;vertical-align:top}th{color:var(--muted)}.scroll{overflow:auto}button.linkbutton{border:0;background:none;color:var(--blue);cursor:pointer;padding:0;font:inherit}.sectionlead{font-size:14px;color:var(--muted);margin-bottom:18px}
@media(max-width:950px){.cards{grid-template-columns:repeat(3,1fr)}.columns,.two{grid-template-columns:1fr}.grid3{grid-template-columns:1fr}.flow:after{display:none}.shell{padding:20px 17px}.calltop{flex-direction:column;gap:5px}.edge{grid-template-columns:1fr}.edge>span{display:none}}@media print{header{background:white;color:var(--ink)}header p{color:var(--muted)}.toolbar,.tabs,.filters{display:none}.shell{max-width:none;padding:12px}.call,.box{break-inside:avoid}pre.raw{max-height:none}}
</style></head><body>
<header><div class="eyebrow">RESEARCH REPORT AGENT / EXECUTION EVIDENCE</div><h1>一步一步，看 Agent 做了什么</h1><p>真实 DeepSeek Flash 请求、真实 MCP 工具执行，以及 Motif 接管记录。这里展示日志里实际发生的操作；缺失的记录会直接标注。</p></header>
<main class="shell"><div class="toolbar"><label for="runSelect">选择一次运行</label><select id="runSelect" aria-label="选择实验运行"></select><span class="muted" id="runCount"></span></div><div id="stats"></div>
<nav class="tabs" role="tablist" aria-label="查看内容"><button data-tab="trace" aria-selected="true">① 逐步工具执行</button><button data-tab="models" aria-selected="false">② 请求大模型</button><button data-tab="motifs" aria-selected="false">③ 学到的 Motif</button><button data-tab="explain" aria-selected="false">④ 怎样读这些记录</button></nav>
<section id="panel"></section><footer id="footer"></footer></main>
<script id="trace-data" type="application/json">__EMBEDDED_DATA__</script>
<script>
'use strict';
const DATA=JSON.parse(document.getElementById('trace-data').textContent);let selected=Math.max(0,DATA.runs.findIndex(r=>r.manifest.mode==='execute'&&r.metrics.report_quality_passed===true)),tab='trace',query='',motifOnly=false;
const TOOL_LABELS={inspect_study:'读取数据与检查字段',plan_analysis:'模型提交分析计划',run_analysis:'执行真实统计计算',verify_analysis:'独立复算统计结果',plan_figures:'模型提交绘图计划',render_figures:'实际渲染与保存图像',verify_figures:'检查图像与数值来源',plan_report:'模型提交报告内容',export_report:'实际排版与导出报告',verify_report:'检查报告页数与数值'};
const hasLearnedTarget=name=>(DATA.library?.artifacts??[]).some(row=>row.to_tool.endsWith('__'+name));
const $=id=>document.getElementById(id),esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty=value=>JSON.stringify(value,null,2),short=name=>String(name??'').replace(/^mcp__research_report__/,''),num=value=>value==null?'未记录':Number(value).toLocaleString('zh-CN'),money=value=>value==null?'未记录':Number(value).toFixed(4),run=()=>DATA.runs[selected];
const raw=(title,value)=>`<details><summary>${esc(title)}</summary><pre class="raw">${esc(typeof value==='string'?value:pretty(value))}</pre></details>`;
function sourceLabel(row){if(row.origin==='motif')return '<span class="pill motif">Motif 生成指令</span>';return '<span class="pill llm">LLM 生成指令</span>';}
function status(row){if(!row.result_events.length)return '<span class="pill warn">未找到返回</span>';return row.error?'<span class="pill bad">错误 / 检查未通过</span>':'<span class="pill ok">已返回</span>';}
function metric(label,value,caption){return `<div class="card"><span>${esc(label)}</span><b>${esc(value)}</b><span>${esc(caption)}</span></div>`;}
function renderStats(){const r=run();if(!r){$('stats').innerHTML='';return;}const m=r.metrics;const qa=m.report_quality_passed===true?'通过':m.report_quality_passed===false?'未通过':'未记录';
$('stats').innerHTML=`<div class="cards">${metric('真实 API 请求',num(m.upstream_requests),'询问云端模型的次数')}${metric('MCP 工具调用',num(m.tool_calls??r.tools.length),'执行程序的次数')}${metric('已验证 Motif 接管',num(m.verified_motif_bypasses),'跳过模型请求的批次')}${metric('自动报告检查',qa,'不等于人工科学质量评审')}${metric('离峰费用估计 / 元',money(m.offpeak_estimate_cny),'以实际 usage 计算；非账单')}${metric('运行时间 / 秒',m.elapsed_seconds==null?'未记录':Number(m.elapsed_seconds).toFixed(1),'包含模型、工具与运行开销')}</div>
<div class="statusline"><span class="pill">${esc(r.manifest.mode)}</span><span class="pill ${m.status==='done'?'ok':'warn'}">${esc(m.status??'未完成 / 未记录')}</span>案例 <code>${esc(r.manifest.case_id)}</code> · 目录 <code>${esc(r.directory)}</code> · 捕获 ${r.requests.length} 份 HTTP 请求 · ${r.event_count} 条 Harness 事件${m.unknown_cost_requests?` · <strong>另有 ${esc(m.unknown_cost_requests)} 次费用未完整结算，保留预算上界</strong>`:''}</div>`;}
function summaries(row){const out=row.output;if(!out)return row.result_text.length?`<div class="snippet">${esc(row.result_text.join('\n').slice(0,1500))}</div>`:'<p class="muted">没有可解析的 JSON 返回；可展开原始事件查看。</p>';
 const pairs=Object.entries(out).filter(([key,value])=>key==='_provenance'?false:['_id','_sha256'].some(end=>key.endsWith(end))||['ok','passed','quality_passed','source_version','path'].includes(key));
 const extra=out.metrics??out.statistics??out.checks??out.figures??out.approved_plan;
 return `<dl class="kv">${pairs.map(([key,value])=>`<div><dt>${esc(key)}</dt><dd>${esc(typeof value==='object'?pretty(value):value)}</dd></div>`).join('')}</dl>${extra?`<div class="snippet" style="margin-top:10px">${esc(pretty(extra).slice(0,1800))}${pretty(extra).length>1800?'\n… 更多内容见完整结果':''}</div>`:''}`;}
function toolCard(row){const req=row.model_request;return `<article class="call ${row.origin==='motif'?'motif-border':'llm-border'}"><div class="calltop"><div><div class="label">工具调用 ${row.number} · Harness 第 ${row.loop||'?'} 轮</div><h3>${esc(TOOL_LABELS[short(row.tool)]??short(row.tool))}</h3><div class="muted"><code>${esc(short(row.tool))}</code></div>${sourceLabel(row)}<span class="pill mcp">真实 MCP</span>${status(row)}</div><div class="muted">${row.origin==='motif'?(row.verified_bypass?'接管结果已验证':'接管尝试；尚未确认结果'):req?`对应真实模型请求 #${req}`:'未在捕获的 HTTP 响应中匹配 call_id'}<br><code>${esc(row.call_id)}</code></div></div><div class="callbody"><div class="columns"><div><div class="label">传给工具的参数</div><pre class="snippet">${esc(pretty(row.arguments))}</pre></div><div><div class="label">工具返回：编号、状态与结果摘要</div>${summaries(row)}</div></div>${row.motif?`<div class="note"><b>为什么本步可以不问模型？</b><br>本次审计记录选择了 <code>${esc(row.motif.motif_id)}</code>。上一步返回的 receipt 提供了唯一参数，模型先前已批准继续；插件还检查了授权、源文件、版本及工具 schema。具体 guard 与来源见审计原文。${raw('展开这一步的 Motif 审计',row.motif)}</div>`:''}${raw('展开完整工具参数与 call 事件',row.call_event)}${raw('展开完整 MCP 返回事件',row.result_events)}${row.output?raw('展开解包后的完整 JSON 结果',row.output):''}</div></article>`;}
function renderTrace(){const r=run();if(!r){$('panel').innerHTML='<div class="empty">尚未找到实际运行记录。生成真实 run 后重新执行构建脚本；查看器不会补造示例数据。</div>';return;}
 const visible=r.tools.filter(row=>(!motifOnly||row.origin==='motif')&&(!query||`${row.tool} ${row.call_id} ${pretty(row.arguments)}`.toLowerCase().includes(query.toLowerCase())));
 $('panel').innerHTML=`<p class="sectionlead">模型负责决定做什么；MCP 把指令交给真正的 Python 程序。绿色条目由 Motif 生成工具指令，蓝色条目由模型生成。两者都实际执行工具。</p><div class="legend"><span><span class="pill llm">LLM</span>已向模型询问下一步</span><span><span class="pill motif">Motif</span>由认证参数流直接续步</span><span><span class="pill mcp">MCP</span>数据计算 / 绘图 / 文件导出</span></div><div class="filters"><input id="filterText" type="search" aria-label="搜索工具名、参数、调用编号" placeholder="搜索工具名、参数、调用编号" value="${esc(query)}"><label><input id="onlyMotif" type="checkbox" ${motifOnly?'checked':''}> 只看 Motif 接管</label><span class="muted">显示 ${visible.length} / ${r.tools.length} 次调用</span></div>${visible.length?visible.map(toolCard).join(''):'<div class="empty">这个筛选条件下没有工具调用。若运行启动失败，可在下方诊断中查看原因。</div>'}<div class="box"><h3>产出的报告与图像</h3>${r.artifacts.length?`<div class="assetlist">${r.artifacts.map(file=>`<a href="${esc(file.href)}" target="_blank" rel="noopener">${esc(file.kind.toUpperCase())} · ${esc(file.name)}</a>`).join('')}</div><p class="muted">这些链接指向构建查看器时实际存在的文件；请一起保留原始运行目录。可能包含中间版本，以 verify_report 与最终交付记录为准。</p>`:'<p class="muted">这个运行没有找到 PDF、DOCX、PNG 或 SVG 文件。</p>'}</div>${r.answer?`<div class="box"><h3>Agent 的最终回答</h3><div class="modelcontent">${esc(r.answer)}</div></div>`:''}${r.diagnostics?`<div class="box"><h3>本次失败诊断</h3>${raw('展开诊断（已防御性脱敏）',r.diagnostics)}</div>`:''}<div class="box"><h3>完整证据</h3>${raw('有效配置 manifest',r.manifest)}${raw('指标 metrics',r.metrics)}${raw('全部 Motif 审计',r.audits)}${raw('全部原始 Harness 事件',r.raw_events)}</div>`;
 $('filterText').addEventListener('input',event=>{const pos=event.target.selectionStart;query=event.target.value;renderTrace();$('filterText').focus();$('filterText').setSelectionRange(pos,pos);});$('onlyMotif').addEventListener('change',event=>{motifOnly=event.target.checked;renderTrace();});}
function renderModels(){const r=run();if(!r){$('panel').innerHTML='<div class="empty">尚无实际模型请求记录。</div>';return;}
 $('panel').innerHTML=`<h2>真正发往 DeepSeek 的 HTTP 请求</h2><div class="note"><b>“请求模型”与“调用工具”是两件事。</b><br>一次模型请求可以返回一条、几条工具指令，也可以只返回最终回答。因此，API 请求数与工具调用数不一定相等。Motif 生成的工具指令不会出现在这里的真实 HTTP 请求列表中。</div><p class="sectionlead">此页直接读取预算代理保存的 request.json / response.txt。工具编号通过模型响应中的 call_id 与 Harness 事件精确对齐；没有匹配证据时不补猜。所有模型思考开关以请求体中的 thinking 为准。</p>${r.requests.length?r.requests.map(req=>{const body=req.request??{},parsed=req.response??{},cost=req.cost??{};return `<article class="call llm-border"><div class="calltop"><div><h3>模型请求 #${req.number}</h3><span class="pill llm">${r.manifest.real_upstream===true?'真实云 API':'HTTP 来源未确认'}</span><span class="pill ${cost.status===200?'ok':'warn'}">HTTP ${esc(cost.status??'未记录')}</span><span class="pill">${esc(body.model??'未记录')}</span></div><div class="muted">${esc(req.request_id)}<br>思考模式：${esc(body.thinking?.type??'未记录')} · 离峰估费 ¥${money(cost.offpeak_estimate_cny)}</div></div><div class="callbody"><p class="muted">输入 ${Array.isArray(body.messages)?body.messages.length:'?'} 条消息 · 工具目录 ${Array.isArray(body.tools)?body.tools.length:'?'} 项 · 返回 ${parsed.tool_calls.length} 条工具指令</p>${parsed.tool_calls.length?`<div class="snippet">${esc(pretty(parsed.tool_calls))}</div>`:''}${parsed.text?`<div class="modelcontent">${esc(parsed.text)}</div>`:''}${raw('展开送给大模型的完整输入（提示词、历史、工具 schema）',body)}${raw('展开模型返回的原始 SSE / JSON',req.response_raw??'响应文件不存在')}${raw('展开实际 token usage 与成本记录',cost)}</div></article>`;}).join(''):'<div class="empty">没有保存下来的实际 HTTP 请求。该运行可能尚未请求模型、启动失败，或复制时缺少 model-requests 目录。请结合 metrics 判断。</div>'}`;}
function renderMotifs(){const library=DATA.library;const r=run();if(!library||!Array.isArray(library.artifacts)){$('panel').innerHTML='<div class="empty">没有可读取的认证库。完成真实普通组训练与独立认证后，再传入 --library 构建。</div>';return;}
 $('panel').innerHTML=`<h2>从真实轨迹中学到的参数传递</h2><p class="sectionlead">下面的边来自库文件中的训练与独立认证 witness。它们说明“上一个工具返回哪个字段，恰好成为下一个工具的哪个参数”；它们不是自动理解任意科研任务的证明。</p><div class="note">先由 LLM 决定统计方法、图型和报告内容，并明确授权确定性续步。插件只尝试库里已学到且认证通过的边；版本、权限、参数或 schema 不匹配时回到模型。这个 benchmark 的工作区文件写入能力是局部扩展，不等于原有只读 core 已普遍支持写入。</div><div class="statusline">库摘要 <code>${esc(library.library_digest)}</code> · 训练 ${esc((library.training_cases??[]).join('、'))} · 独立认证 ${esc(library.certification_case)}</div>${library.artifacts.map(motif=>{const hits=r?r.tools.filter(row=>row.motif?.motif_id===motif.motif_id).length:0;return `<article class="box"><h3>${esc(motif.motif_id)}</h3><div class="edge"><div><small>先前工具的返回字段</small>${esc(short(motif.from_tool))}<br><strong>${esc(motif.from_field)}</strong></div><span>→</span><div><small>后续工具的唯一参数</small>${esc(short(motif.to_tool))}<br><strong>${esc(motif.to_param)}</strong></div></div><p class="muted">当前选中运行实际接管 ${hits} 次。参数取实际返回的内容寻址编号，不复用旧题的数据值。</p>${(motif.training_evidence??[]).map(w=>`<div class="witness"><span class="pill">训练证据</span><b>${esc(w.case_id)}</b> · ${esc(w.run_id)}${raw('查看调用编号与输入输出哈希 witness',w)}</div>`).join('')}<div class="witness"><span class="pill motif">独立认证</span><b>${esc(motif.certification_evidence?.case_id)}</b>${raw('查看认证 witness',motif.certification_evidence)}</div>${raw('完整 Motif 编译产物',motif)}</article>`;}).join('')}<div class="box">${raw('完整库（含实际工具 schema）',library)}</div>`;}
function renderExplain(){$('panel').innerHTML=`<h2>先认识两种“请求”</h2><div class="two"><div class="box"><span class="pill llm">请求 LLM</span><h3>“下一步应该做什么？”</h3><p>DSH 把用户需求、已有数据摘要、历史结果和工具说明发送给 DeepSeek。模型可能决定统计方法、图的类型、报告篇幅，或返回一条工具指令。这一步消耗模型 token。</p><pre class="snippet">输入：配对试验的数据与用户要求\n模型决定：分析同一受试者的前后变化\n输出：plan_analysis(study_id, plan)</pre></div><div class="box"><span class="pill mcp">调用 MCP 工具</span><h3>“请把这件事实际做出来。”</h3><p>DSH 通过 MCP 协议把工具名和参数发给本地 Python 服务。NumPy / SciPy 等实际计算，Matplotlib 实际绘图，文档程序实际写出 PDF。原始观测数据是生成的，工具执行不是模拟响应。</p><pre class="snippet">工具：run_analysis\n参数：plan_id = 上一步返回的计划编号\n返回：analysis_id、统计值、版本与校验信息</pre></div></div><h2>三个关键语义决定，仍交给模型</h2><p class="sectionlead">这是帮助理解的机制示意。每次运行实际走了哪些步骤，以“逐步工具执行”和“请求大模型”页为准；不是声称每条路径都已学到或每次都由 Motif 执行。</p><div class="grid3"><div class="flow"><b>01 · 怎样分析数据</b><div class="step llm">LLM 看数据与研究问题<br>选择独立组、配对或回归设计</div><div class="arrow">↓ 输出并批准分析计划</div><div class="step mcp">真实工具执行统计 → 数值复核</div><div class="step motif">若已学到且守卫通过<br>receipt 参数流可由 Motif 接管</div></div><div class="flow"><b>02 · 怎样把结果画出来</b><div class="step llm">LLM 决定图型、组合、标题<br>适配研究问题和用户偏好</div><div class="arrow">↓ 输出并批准绘图计划</div><div class="step mcp">真实工具渲染 → 文件与图像检查</div><div class="step motif">确定的绘图编号传递可复用<br>不替模型选择科研表达方式</div></div><div class="flow"><b>03 · 怎样形成报告</b><div class="step llm">LLM 写解释、局限和后续建议<br>选择用户要求的页数与格式</div><div class="arrow">↓ 输出并批准报告计划</div><div class="step mcp">真实工具导出 → 页数与数值复核</div><div class="step ${hasLearnedTarget('export_report')?'motif':'llm'}">${hasLearnedTarget('export_report')?'当前库含报告续步候选，仍需逐步守卫':'本次库没有认证报告续步 Motif'}<br>${hasLearnedTarget('export_report')?'是否接管以实际审计为准':'报告导出与复核的指令仍由 LLM 给出'}</div></div></div><div class="box" style="margin-top:22px"><h3>日志中的几个基本词</h3><div class="scroll"><table><thead><tr><th>字段 / 概念</th><th>通俗解释</th></tr></thead><tbody><tr><td>arguments / 参数</td><td>交给工具的输入，例如“使用哪个分析计划”。它不是代码文件名，也不必由模型每次重新计算。</td></tr><tr><td>结果字段</td><td>工具返回 JSON 中有名字的一项，例如 <code>analysis_id</code> 是刚算出的结果编号。</td></tr><tr><td>receipt / 内容寻址记录</td><td>保存在本次工作区的可核验记录。编号绑定内容，记录还带有数据版本和后续授权。</td></tr><tr><td>call_id</td><td>一次工具调用的唯一编号。用它把“谁生成指令”“工具实际返回什么”“Motif 是否验证成功”对齐。</td></tr><tr><td>LLM / MCP / Motif</td><td>LLM 决策；MCP 传递实际工具请求；Motif 在条件允许时生成已确定的工具指令。它们不是三个互相替代的模型。</td></tr><tr><td>verified_motif_bypasses</td><td>插件生成指令并且对应工具结果通过检查的批次。不能直接当作人民币节省，也不等于跳过了工具计算。</td></tr><tr><td>report_quality_passed</td><td>自动检查通过：例如文件、页数和关键数值。报告的科学表述、图是否易懂，还需要人工或另外的质量评审。</td></tr><tr><td>baseline / execute / pilot</td><td>baseline 是普通 DSH；execute 允许使用认证 Motif；pilot 通常是运行目录的试跑标记。启动失败与修复重跑也保留，不算成功收益。</td></tr><tr><td>费用估计</td><td>按 API 返回的 token usage 和记录价格计算。离峰估计、峰值保守记账和平台账单应区分；缺失 usage 会保留预留上界。</td></tr></tbody></table></div></div><div class="note warning"><b>如何判断优化有效？</b><br>先确认同一任务两组的输入哈希、模型与工具配置相同，报告都达到质量门槛，再比较真实 API 次数、输入/输出与缓存 token、总费用和耗时。还要考虑试跑、学习认证开销以及模型输出的随机性。不能只拿“跳过几次请求”宣称普遍有效。</div>`;}
function render(){renderStats();document.querySelectorAll('[data-tab]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.tab===tab)));if(tab==='trace')renderTrace();if(tab==='models')renderModels();if(tab==='motifs')renderMotifs();if(tab==='explain')renderExplain();}
DATA.runs.forEach((r,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=`${r.manifest.case_id} · ${r.manifest.mode} · ${r.directory} · ${r.metrics.status??'未完成'}`;$('runSelect').appendChild(option);});$('runSelect').value=String(selected);$('runSelect').disabled=!DATA.runs.length;$('runSelect').addEventListener('change',event=>{selected=Number(event.target.value);query='';render();});document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{tab=button.dataset.tab;render();}));$('runCount').textContent=`${DATA.runs.length} 次实际运行；包含失败与试跑`;$('footer').textContent=`离线构建时间（UTC）：${DATA.built_utc}。无外网依赖、无 fetch；仅展示实际文件。原始请求含本次任务内容，请保留在私有实验目录。`;render();
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.runs_root.is_dir():
        parser.error("--runs-root must be an existing directory of actual runs")
    result = build(args.runs_root.resolve(), args.library.resolve() if args.library else None, args.output.resolve())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
