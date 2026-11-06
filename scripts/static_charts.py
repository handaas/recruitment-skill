#!/usr/bin/env python3
"""Static-first chart embedding for the HandaaS report renderer.

Renders every empty ``.chart-canvas`` placeholder in a finished HTML report into
a real, viewable SVG at report-generation time, using the skill-local ECharts
bundle and the system ``node`` binary in *one* subprocess per report. The
browser later upgrades the same placeholder to the interactive ECharts layer;
until (and unless) that upgrade succeeds, the static SVG stays visible, so the
report shows charts even with JavaScript disabled.

Contract
--------
* ``CHART_OPTIONS_JS`` defines ``handaasChartOption(spec)`` — the single option
  factory shared by the static (Node/SSR) renderer and the browser bootstrap.
  Initial animations are disabled (including the gauge ``valueAnimation``) so
  the first synchronous ``setOption`` already produces the final geometry.
* ``embed_static_charts(document, vendor_path)`` mutates nothing; it returns the
  document with, for each empty ``.chart-canvas``:
  - a ``<div class="chart-frame" data-chart-state="static">`` wrapper holding a
    ``<div class="chart-static">`` with the deterministic SSR SVG (ids prefixed
    ``static-chart-<ordinal>-``), the original ``.chart-canvas`` (hidden-but-
    sized overlay for the interactive layer) and a ``<p class="chart-status">``
    for interaction status;
  - shared frame CSS and the ``CHART_OPTIONS_JS`` script injected just before
    the document's first ``<script>`` tag (which precedes the embedded vendor),
    so options are always defined before vendor/bootstrap execution.
  Documents without any chart placeholder are returned unchanged; no Node
  subprocess is started and no Node installation is required in that case.
* Any failure (missing vendor/Node, unparseable or inconsistent specs, renderer
  errors) raises ``RuntimeError`` — reports are never emitted with silently
  blank charts. Subprocess stderr is sanitized before it reaches the error
  message.

Only the Python standard library is used; no new npm/Python dependencies.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import shutil
import subprocess
from typing import Any, Dict, List, Sequence

__all__ = ["CHART_OPTIONS_JS", "embed_static_charts"]


# --------------------------------------------------------------------------- #
# Shared option factory (browser + SSR). Keep styles/values identical to the
# original renderer bootstrap; add animation:false for real initial geometry.
# --------------------------------------------------------------------------- #

CHART_OPTIONS_JS = r"""function handaasChartOption(spec){
  if(!spec || ['line','bar','pie','gauge','radar'].indexOf(spec.type)<0){return null;}
  var PALETTE=['#0b5ca8','#0284c7','#0b3768','#d97706','#059669','#dc2626','#7c3aed','#db2777','#0891b2','#65a30d'];
  var FONTS="-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif";
  var opt={animation:false,color:PALETTE,tooltip:{trigger: spec.type==='pie'?'item':'axis'},textStyle:{fontFamily:FONTS,fontSize:12,color:'#334155'},grid:{left:48,right:24,top:30,bottom:40},legend:{top:0,textStyle:{fontSize:11}}};
  if(spec.type==='line'){
    opt.xAxis={type:'category',data:spec.x,axisLabel:{fontSize:11,interval:0,rotate: spec.x && spec.x.length>6?35:0}};
    opt.yAxis={type:'value'};
    opt.series=spec.series.map(function(s){return{name:s.name,type:'line',smooth:true,areaStyle: spec.area?{opacity:0.18}:undefined,stack: spec.stack?s.name:undefined,data:s.data,label:{show:true,position:'top',fontSize:11}};});
    if(spec.stack){opt.tooltip={trigger:'axis'};}
  }else if(spec.type==='bar'){
    var horiz=spec.orient==='h';
    var cats=spec.names, vals=spec.values;
    if(horiz){opt.yAxis={type:'category',data:cats,axisLabel:{fontSize:11}};opt.xAxis={type:'value'};opt.grid={left:120,right:30,top:20,bottom:30};}
    else{opt.xAxis={type:'category',data:cats,axisLabel:{fontSize:11,interval:0,rotate: cats&&cats.length>6?35:0}};opt.yAxis={type:'value'};}
    opt.series=[{type:'bar',data:vals,itemStyle:{color:PALETTE[0]},label:{show:true,position: horiz?'right':'top',fontSize:11},barMaxWidth:42}];
    opt.tooltip={trigger:'axis',axisPointer:{type:'shadow'}};
  }else if(spec.type==='pie'){
    opt.series=[{type:'pie',radius: spec.donut?['42%','68%']:'68%',center:['50%','55%'],data:spec.data,itemStyle:{borderColor:'#fff',borderWidth:2},label:{fontSize:11,formatter:'{b}: {c} ({d}%)'}}];
    opt.legend={bottom:0,textStyle:{fontSize:11}};
    opt.tooltip={trigger:'item',formatter:'{b}: {c} ({d}%)'};
  }else if(spec.type==='gauge'){
    var v=spec.value, mx=spec.max||100;
    var col=v/mx>0.66?'#dc2626':(v/mx>0.33?'#d97706':'#059669');
    opt.series=[{type:'gauge',min:0,max:mx,progress:{show:true,width:14,itemStyle:{color:col}},axisLine:{lineStyle:{width:14}},axisTick:{show:false},splitLine:{length:8,lineStyle:{color:'#fff'}},pointer:{width:5},detail:{valueAnimation:false,formatter:'{value}',fontSize:28,color:col,offsetCenter:[0,'30%']},data:[{value:v,name:spec.level||''}],title:{fontSize:13,color:'#475569',offsetCenter:[0,'62%']}}];
  }else if(spec.type==='radar'){
    opt.radar={indicator:spec.indicators,radius:'62%',axisName:{color:'#475569',fontSize:11},splitArea:{areaStyle:{color:['#f8fbff','#eef4fb']}}};
    opt.series=[{type:'radar',areaStyle:{opacity:0.18},data:spec.series}];
  }
  return opt;
}
"""


# --------------------------------------------------------------------------- #
# Shared frame CSS. Injected before the first <script> tag so it always lands
# after (and therefore wins over) renderer template CSS at equal specificity.
# The static layer is visible by default; the interactive canvas overlay is
# hidden but sized, and is revealed only when frame[data-chart-state="ready"].
# Print always uses the static layer.
# --------------------------------------------------------------------------- #

_FRAME_CSS = """<style>
.chart-frame{position:relative;width:100%;height:300px;}
.chart-box-gauge .chart-frame{height:240px;}
.chart-static{position:absolute;top:0;left:0;width:100%;height:100%;overflow:hidden;}
.chart-static svg{display:block;width:100%;height:100%;}
.chart-frame .chart-canvas{position:absolute;top:0;left:0;width:100%;height:100% !important;visibility:hidden;z-index:1;}
.chart-frame[data-chart-state="ready"] .chart-canvas{visibility:visible;}
.chart-frame[data-chart-state="ready"] .chart-static{visibility:hidden;}
.chart-frame .chart-status{position:absolute;left:0;right:0;bottom:0;margin:0;padding:2px 8px;font-size:11px;color:#64748b;text-align:center;background:rgba(255,255,255,.88);z-index:2;}
.chart-frame .chart-status:empty{display:none;}
@media print{
  .chart-frame{height:auto;overflow:visible;}
  .chart-frame .chart-canvas{display:none !important;visibility:hidden;}
  .chart-frame .chart-static{position:static;display:block !important;visibility:visible !important;}
  .chart-frame .chart-status{display:none;}
  .chart-static svg{height:auto;}
}
</style>"""


# --------------------------------------------------------------------------- #
# Node SSR runner: one subprocess per report, jobs as JSON on stdin, SVGs as
# JSON on stdout. Only JSON data crosses the process boundary — never report
# markup — and the same handaasChartOption factory drives both layers.
# --------------------------------------------------------------------------- #

_NODE_SSR_JS = (
    r"""
var vendorPath=process.argv[1];
var echarts;
try{echarts=require(vendorPath);}catch(e){process.stderr.write('load');process.exit(3);}
if(!echarts||typeof echarts.init!=='function'){process.stderr.write('load');process.exit(3);}
"""
    + CHART_OPTIONS_JS
    + r"""
var input='';
process.stdin.setEncoding('utf8');
process.stdin.on('data',function(chunk){input+=chunk;});
process.stdin.on('end',function(){
  var jobs=null;
  try{jobs=JSON.parse(input);}catch(e){process.stderr.write('parse');process.exit(3);}
  if(!Array.isArray(jobs)){process.stderr.write('parse');process.exit(3);}
  var out=[];
  try{
    for(var i=0;i<jobs.length;i++){
      var job=jobs[i];
      var chart=echarts.init(null,null,{renderer:'svg',ssr:true,width:job.width,height:job.height});
      try{
        var opt=handaasChartOption(job.spec);
        if(!opt||typeof opt!=='object'){throw new Error('unsupported chart type');}
        chart.setOption(opt);
        var svg=chart.renderToSVGString();
        if(!svg||String(svg).indexOf('<svg')<0){throw new Error('empty svg');}
        out.push(svg);
      }finally{
        try{chart.dispose();}catch(ignored){}
      }
    }
  }catch(e){
    process.stderr.write('render');
    process.exit(3);
  }
  process.stdout.write(JSON.stringify(out));
});
"""
)


_CANVAS_RE = re.compile(r'<div class="chart-canvas" data-chart="([^"]+)" data-spec="([^"]*)"\s*></div>')
_ID_ATTR_RE = re.compile(r'(?<![\w-])id="([^"]*)"')
_URL_REF_RE = re.compile(r'(url\(["\']?)#([^"\')]+)')
_HREF_REF_RE = re.compile(r'(xlink:href|href)="#([^"]+)"')
_FIRST_SCRIPT_RE = re.compile(r'<script\b')

# Fixed, pre-approved failure descriptions keyed by the category the node
# runner writes to stderr. Raw stderr is never surfaced.
_NODE_FAILURE_DETAIL = {
    "load": "本地 ECharts 图表库无法被渲染进程加载",
    "parse": "图表渲染任务数据无法被渲染进程解析",
    "render": "静态图表 SVG 渲染失败",
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _prefix_svg_ids(svg: str, prefix: str) -> str:
    """Prefix every SVG id attribute and every url(#id)/href="#id" reference
    with ``prefix`` so static SVGs can never collide with the interactive
    ECharts SVG ids. Only attribute/reference contexts are rewritten — literal
    label text is never touched."""
    def rewrite_tag(match: re.Match[str]) -> str:
        tag = _ID_ATTR_RE.sub(lambda m: f'id="{prefix}{m.group(1)}"', match.group(0))
        tag = _URL_REF_RE.sub(lambda m: f'{m.group(1)}#{prefix}{m.group(2)}', tag)
        return _HREF_REF_RE.sub(lambda m: f'{m.group(1)}="#{prefix}{m.group(2)}"', tag)

    return re.sub(r"<[^>]+>", rewrite_tag, svg)


def _render_svg_batch(jobs: Sequence[Dict[str, Any]], vendor_path: pathlib.Path) -> List[str]:
    """Render all jobs in a single node subprocess; raise on any failure."""
    vendor = vendor_path.resolve()
    if not vendor.is_file():
        raise RuntimeError(f"缺少本地 ECharts 图表库：{vendor}；无法生成静态图表。")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("生成静态图表需要 Node.js，但当前环境中找不到 node 可执行文件。")
    payload = json.dumps(jobs, ensure_ascii=False, separators=(",", ":"))
    try:
        result = subprocess.run(
            [node, "-e", _NODE_SSR_JS, str(vendor)],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("生成静态图表需要 Node.js，但当前环境中找不到 node 可执行文件。") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("静态图表渲染超时，无法生成图表报告。") from exc
    if result.returncode != 0:
        # Never surface raw stderr: only a fixed phase category + exit code.
        # The node script emits exactly one of 'load'/'parse'/'render'.
        category = (result.stderr or "").strip().splitlines()
        category = category[0].strip() if category else ""
        detail = _NODE_FAILURE_DETAIL.get(category, "未知原因")
        raise RuntimeError(f"静态图表渲染失败（node 退出码 {result.returncode}）：{detail}。")
    try:
        svgs = json.loads(result.stdout or "")
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("静态图表渲染返回了无法解析的结果。") from exc
    if not isinstance(svgs, list) or len(svgs) != len(jobs) or not all(isinstance(s, str) and s.strip() for s in svgs):
        raise RuntimeError("静态图表渲染结果不完整或为空，无法生成图表报告。")
    return svgs


def _inject_shared_head(document: str) -> str:
    """Insert frame CSS + CHART_OPTIONS_JS before the first <script> tag, so the
    option factory is defined before vendor/bootstrap execution."""
    inject = _FRAME_CSS + "\n" + "<script>" + CHART_OPTIONS_JS + "</script>"
    m = _FIRST_SCRIPT_RE.search(document)
    if m:
        return document[: m.start()] + inject + "\n" + document[m.start():]
    for anchor in ("</head>", "</body>"):
        pos = document.find(anchor)
        if pos != -1:
            return document[:pos] + inject + "\n" + document[pos:]
    return document + "\n" + inject


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def embed_static_charts(document: str, vendor_path: pathlib.Path | str) -> str:
    """Wrap every empty .chart-canvas in a static-first chart frame and inject
    the shared frame CSS + option factory. No-op (no Node needed) for documents
    without charts; raises RuntimeError instead of emitting blank charts."""
    if 'class="chart-frame"' in document:
        raise RuntimeError("报告已包含静态图表框架，不能重复嵌入。")
    total = document.count('<div class="chart-canvas"')
    if total == 0:
        return document
    matches = list(_CANVAS_RE.finditer(document))
    if total != len(matches):
        raise RuntimeError(
            f"报告包含 {total} 个图表容器，但仅 {len(matches)} 个为空占位，无法生成静态图表。"
        )
    jobs: List[Dict[str, Any]] = []
    for ordinal, match in enumerate(matches):
        chart_type = match.group(1)
        try:
            spec = json.loads(html.unescape(match.group(2)))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"第 {ordinal + 1} 个图表（{chart_type}）的 data-spec 无法解析，不能生成静态图表。"
            ) from exc
        if not isinstance(spec, dict) or spec.get("type") != chart_type:
            raise RuntimeError(
                f"第 {ordinal + 1} 个图表的 data-spec 与 data-chart 不一致，不能生成静态图表。"
            )
        is_gauge = chart_type == "gauge"
        jobs.append(
            {
                "spec": spec,
                "width": 360 if is_gauge else 984,
                "height": 240 if is_gauge else 300,
                "prefix": f"static-chart-{ordinal}-",
            }
        )
    svgs = _render_svg_batch(jobs, pathlib.Path(vendor_path))
    chunks: List[str] = []
    last = 0
    for ordinal, (match, job) in enumerate(zip(matches, jobs)):
        chunks.append(document[last:match.start()])
        svg = _prefix_svg_ids(svgs[ordinal], job["prefix"])
        chunks.append(
            '<div class="chart-frame" data-chart-state="static">'
            f'<div class="chart-static">{svg}</div>'
            f'{match.group(0)}'
            '<p class="chart-status" aria-live="polite"></p>'
            '</div>'
        )
        last = match.end()
    chunks.append(document[last:])
    return _inject_shared_head("".join(chunks))
