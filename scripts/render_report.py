#!/usr/bin/env python3
"""Render a HandaaS data report as standalone HTML or Markdown.

This renderer implements the unified professional research-report visual style
shared across all handaas-skills (A4-like white pages, grey striped top rule,
blue report banner, left cover sidebar with catalogue/scope, navy section
headings, dark-blue table headers, light-blue zebra rows, print-friendly page
breaks). It consumes the unified report JSON skeleton defined in AGENTS.md.

Usage::

    python render_report.py --input report.json --output report.html
    python render_report.py --input report.json --output report.md
    python render_report.py --input report.json --output report.pdf
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import sys
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from common import REPORT_TYPE, json_dumps


# --------------------------------------------------------------------------- #
# IO helpers
# --------------------------------------------------------------------------- #

def load_payload(input_path: str | None) -> Dict[str, Any]:
    if input_path:
        path = pathlib.Path(input_path).expanduser()
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = sys.stdin.read().strip()
        if not raw:
            raise SystemExit("请提供 --input <result.json> 或通过 stdin 传入 JSON")
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit("报告输入必须是 JSON object")
    return data


# --------------------------------------------------------------------------- #
# Generic formatting helpers
# --------------------------------------------------------------------------- #

def as_list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json_dumps(value, pretty=True)
    return str(value)


def esc(value: Any) -> str:
    return html.escape(text(value), quote=True)


def compact(value: Any, limit: int = 0) -> str:
    t = " ".join(text(value).replace("\n", " ").split()).strip(" ；;。")
    if limit and len(t) > limit:
        return t[: limit - 1].rstrip() + "…"
    return t


def infer_title(data: Mapping[str, Any], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if data.get("title"):
        return str(data["title"])
    subject = data.get("subject") or {}
    name = subject.get("enterprise") or subject.get("matchKeyword") or subject.get("match_raw")
    return f"{name or '目标'} 数据分析报告" if name else "HandaaS 数据分析报告"


def infer_banner(data: Mapping[str, Any]) -> str:
    return str(data.get("banner") or data.get("report_title") or "HandaaS 数据分析报告")


# --------------------------------------------------------------------------- #
# Table rendering
# --------------------------------------------------------------------------- #


def _safe_unwrap_json(value: Any) -> Any:
    """Safety net: if a cell value is a JSON string (e.g. MCP returned a
    stringified object), parse it into a readable scalar."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if len(stripped) <= 3 or stripped[0] != "{" or stripped[-1] != "}":
        return value
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return value
    if not isinstance(obj, dict):
        return value
    # Prefer common readable fields
    for field in ("value", "name", "label", "text", "title"):
        if obj.get(field) is not None:
            return obj[field]
    # Address-like objects
    parts = [obj.get("province"), obj.get("city"), obj.get("district")]
    joined = "".join(str(p) for p in parts if p)
    if joined:
        return joined
    return value


def _cell_html(value: Any) -> str:
    """Render a table cell; render http(s) URLs as clickable links."""
    if value in (None, ""):
        return "-"
    value = _safe_unwrap_json(value)
    s = text(value)
    if isinstance(value, str) and (value.startswith("http://") or value.startswith("https://")):
        return f'<a class="source-link" href="{esc(value)}" target="_blank" rel="noopener">{esc(value)}</a>'
    return esc(s)


def render_table(rows: Sequence[Any], columns: Sequence[tuple[str, str]] | None = None) -> str:
    rows = [r for r in rows if isinstance(r, dict)] if rows else []
    if not rows:
        return '<p class="muted">暂无数据</p>'
    if not columns:
        columns = [(str(k), str(k)) for k in rows[0].keys()]
    # Auto-detect column order: a column pair may be (data_key, display_label)
    # or (display_label, data_key). Detect by checking which side matches an
    # actual key in the first data row, so compose specs written in either
    # convention render correctly. Falls back to (first=label, second=key).
    sample = rows[0] if rows else {}
    norm_cols = []
    for pair in columns:
        a, b = (list(pair) + [None, None])[:2]
        a_ok = isinstance(a, str) and a in sample
        b_ok = isinstance(b, str) and b in sample
        if a_ok and not b_ok:
            key, label = a, (b if b else a)  # (key, label)
        elif b_ok and not a_ok:
            key, label = b, (a if a else b)  # (label, key) -> normalize
        elif a_ok and b_ok:
            key, label = a, b  # both are keys; use first as key
        else:
            # Neither matches a real key; assume (key, label) convention
            key, label = (a or ""), (b or a or "")
        norm_cols.append((key, label))
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in norm_cols)
    body = []
    for row in rows:
        cells = "".join(f"<td>{_cell_html(row.get(key))}</td>" for key, _ in norm_cols)
        body.append(f"<tr>{cells}</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def render_kv_grid(data: Mapping[str, Any]) -> str:
    items = [(k, v) for k, v in data.items() if v not in (None, "", [], {})]
    if not items:
        return '<p class="muted">暂无</p>'
    cells = "".join(
        f'<div class="biz-scope-item"><span>{esc(k)}</span><strong>{esc(v)}</strong></div>'
        for k, v in items
    )
    return f'<div class="biz-scope">{cells}</div>'


def render_info_list(data: Mapping[str, Any]) -> str:
    """Professional definition-list for body sections (caliber/source).

    Left label strip (deep-blue accent) + right content that wraps naturally.
    Use this for key/value info inside report body chapters instead of the
    compact card grid, which is reserved for the cover sidebar.
    """
    items = [(k, v) for k, v in data.items() if v not in (None, "", [], {})]
    if not items:
        return '<p class="muted">暂无</p>'
    rows = "".join(
        f'<div class="info-row"><span class="info-label">{esc(CALIBER_LABELS.get(k, k))}</span><span class="info-value">{esc(v)}</span></div>'
        for k, v in items
    )
    return f'<div class="info-list">{rows}</div>'


def render_metrics(metrics: Sequence[Any]) -> str:
    if not metrics:
        return ""
    cells = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        val = esc(m.get("value", "-"))
        label = esc(m.get("label", ""))
        delta = m.get("delta") or m.get("trend")
        # delta 放在标签下方独立行，无 delta 时预留占位
        tag_html = '<span class="m-tag"></span>'
        if delta:
            d = str(delta)
            if any(c in d for c in "↑▲增升涨高"):
                tag_html = f'<span class="m-tag t-up">{esc(d)}</span>'
            elif any(c in d for c in "↓▼减降跌低"):
                tag_html = f'<span class="m-tag t-down">{esc(d)}</span>'
            else:
                tag_html = f'<span class="m-tag t-neutral">{esc(d)}</span>'
        cells.append(f'<div class="biz-metric"><span class="m-name">{label}</span>{tag_html}<span class="m-value">{val}</span></div>')
    remainder = len(cells) % 4
    if remainder:
        for _ in range(4 - remainder):
            cells.append('<div class="biz-metric-empty"></div>')
    return f'<div class="biz-metrics">{"".join(cells)}</div>' if cells else ""


def render_insights(insights: Sequence[Any]) -> str:
    cards = []
    for item in insights or []:
        if not isinstance(item, dict):
            continue
        cards.append(
            f'''<article class="structural-feature-card">
  <h3>{esc(item.get("feature") or "")}</h3>
  <p class="structural-evidence">{esc(item.get("evidence") or "")}</p>
  <p>{esc(item.get("interpretation") or "")}</p>
</article>'''
        )
    return f'<div class="structural-feature-grid">{"".join(cards)}</div>' if cards else '<p class="muted">暂无</p>'


def render_records(records: Sequence[Any]) -> str:
    records = [r for r in records if isinstance(r, dict)]
    if not records:
        return '<p class="muted">暂无</p>'
    keys = list(records[0].keys())
    columns = [(k, k) for k in keys]
    return render_table(records, columns)


# --------------------------------------------------------------------------- #
# ECharts embedding + chart-box rendering
# --------------------------------------------------------------------------- #

ECHARTS_VENDOR_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "assets" / "vendor" / "echarts.min.js"
)
ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"


def _echarts_inline_or_cdn() -> str:
    """Inline the vendored ECharts bundle; fall back to a CDN script tag."""
    try:
        if ECHARTS_VENDOR_PATH.exists():
            return ECHARTS_VENDOR_PATH.read_text(encoding="utf-8")
    except Exception:
        pass
    return f'document.write("ECharts offline bundle missing. See assets/vendor/echarts.min.js. CDN fallback loaded.");var s=document.createElement("script");s.src="{ECHARTS_CDN}";document.head.appendChild(s);'


# Lightweight data-driven chart bootstrapper. Reads data-spec JSON from each
# .chart-canvas and renders the matching ECharts option.
_HANDAAS_CHART_JS = r"""
(function(){
  window.__echarts_instances=[];
  function boot(){
    if(typeof echarts==='undefined'){return;}
    var PALETTE=['#0b5ca8','#0284c7','#0b3768','#d97706','#059669','#dc2626','#7c3aed','#db2777','#0891b2','#65a30d'];
    var FONTS='-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif';
    document.querySelectorAll('.chart-canvas').forEach(function(el){
      var raw=el.getAttribute('data-spec'); if(!raw){return;}
      var spec; try{spec=JSON.parse(raw.replace(/&quot;/g,'"').replace(/&amp;/g,'&'));}catch(e){return;}
      var chart=echarts.init(el,null,{renderer:'svg'});
      window.__echarts_instances.push(chart);
      var opt={color:PALETTE,tooltip:{trigger: spec.type==='pie'?'item':'axis'},textStyle:{fontFamily:FONTS,fontSize:12,color:'#334155'},grid:{left:48,right:24,top:30,bottom:40},legend:{top:0,textStyle:{fontSize:11}}};
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
        opt.series=[{type:'gauge',min:0,max:mx,progress:{show:true,width:14,itemStyle:{color:col}},axisLine:{lineStyle:{width:14}},axisTick:{show:false},splitLine:{length:8,lineStyle:{color:'#fff'}},pointer:{width:5},detail:{valueAnimation:true,formatter:'{value}',fontSize:28,color:col,offsetCenter:[0,'30%']},data:[{value:v,name:spec.level||''}],title:{fontSize:13,color:'#475569',offsetCenter:[0,'62%']}}];
      }else if(spec.type==='radar'){
        opt.radar={indicator:spec.indicators,radius:'62%',axisName:{color:'#475569',fontSize:11},splitArea:{areaStyle:{color:['#f8fbff','#eef4fb']}}};
        opt.series=[{type:'radar',areaStyle:{opacity:0.18},data:spec.series}];
      }
      chart.setOption(opt);
      window.addEventListener('resize',function(){chart.resize();});
    });
  }
  if(document.readyState!=='loading'){boot();}else{document.addEventListener('DOMContentLoaded',boot);}
  window.__echarts_resize_all=function(){
    (window.__echarts_instances||[]).forEach(function(c){try{c.resize();}catch(e){}});
  };
})();
"""


def _load_echarts() -> str:
    """Return the ECharts JS to embed inline; fall back to a CDN <script src>."""
    try:
        if ECHARTS_VENDOR_PATH.exists():
            return ECHARTS_VENDOR_PATH.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""  # caller falls back to CDN tag


def _num(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("万", ""))
    except (TypeError, ValueError):
        return 0.0


def _chart_fallback_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[tuple[str, str]]) -> str:
    """Data table shown below the chart (also the no-JS fallback)."""
    return f'<details class="chart-data"><summary>数据明细</summary>{render_table(rows, columns)}</details>'


def _looks_temporal(values: Sequence[str]) -> bool:
    """Detect if x-axis values are time-like (years, YYYY-MM, dates)."""
    if not values:
        return False
    import re as _re
    cnt = 0
    for v in values:
        s = str(v).strip()
        # 4-digit year, YYYY-MM, YYYY-MM-DD, or YYYY年
        if _re.match(r"^\d{4}([-/]\d{1,2}([-/]\d{1,2})?)?(年)?$", s):
            cnt += 1
    return cnt >= len(values) * 0.6


def _sort_rows_by_time(rows: Sequence[Mapping[str, Any]], x_key: str) -> list:
    """Sort rows by their x_key value in ascending chronological order.

    Handles years (2017), YYYY-MM (2023-08), YYYY-MM-DD, and YYYY年.
    Returns a new sorted list; original order preserved if not temporal.
    """
    out = list(rows)
    vals = [str(r.get(x_key, "")).strip() for r in out]
    if not _looks_temporal(vals):
        return out

    def sort_key(v: str) -> tuple:
        import re as _re
        s = str(v).strip().rstrip("年")
        # Normalize to comparable tuple of ints
        parts = _re.split(r"[-/]", s)
        try:
            return tuple(int(p) for p in parts)
        except ValueError:
            return (9999,)

    return [r for _, r in sorted(enumerate(out), key=lambda iv: sort_key(vals[iv[0]]))]


def chart_line(title: str, rows: Sequence[Mapping[str, Any]], x_key: str, y_key: str, *, area: bool = False, columns: Sequence[tuple[str, str]] | None = None) -> str:
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return '<p class="muted">暂无数据</p>'
    rows = _sort_rows_by_time(rows, x_key)
    cols = columns or [(x_key, x_key), (y_key, y_key)]
    data = [{"name": text(r.get(x_key)), "value": _num(r.get(y_key))} for r in rows]
    spec = {"type": "line", "area": area, "x": [d["name"] for d in data], "series": [{"name": title, "data": [d["value"] for d in data]}]}
    head = f'<h4 class="chart-title">{esc(title)}</h4>' if title else ""
    return f'<div class="chart-box">{head}<div class="chart-canvas" data-chart="line" data-spec="{esc(json_dumps(spec))}"></div>{_chart_fallback_table(rows, cols)}</div>'


def chart_multi_line(title: str, rows: Sequence[Mapping[str, Any]], x_key: str, series_keys: Sequence[str], *, area: bool = False, columns: Sequence[tuple[str, str]] | None = None) -> str:
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return '<p class="muted">暂无数据</p>'
    rows = _sort_rows_by_time(rows, x_key)
    cols = columns or [(x_key, x_key)] + [(k, k) for k in series_keys]
    x = [text(r.get(x_key)) for r in rows]
    series = [{"name": k, "data": [_num(r.get(k)) for r in rows]} for k in series_keys]
    spec = {"type": "line", "area": area, "stack": area, "x": x, "series": series}
    head = f'<h4 class="chart-title">{esc(title)}</h4>' if title else ""
    return f'<div class="chart-box">{head}<div class="chart-canvas" data-chart="line" data-spec="{esc(json_dumps(spec))}"></div>{_chart_fallback_table(rows, cols)}</div>'


def chart_bar(title: str, rows: Sequence[Mapping[str, Any]], name_key: str, value_key: str, *, orient: str = "v", columns: Sequence[tuple[str, str]] | None = None) -> str:
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return '<p class="muted">暂无数据</p>'
    cols = columns or [(name_key, name_key), (value_key, value_key)]
    data = [{"name": text(r.get(name_key)), "value": _num(r.get(value_key))} for r in rows]
    spec = {"type": "bar", "orient": orient, "names": [d["name"] for d in data], "values": [d["value"] for d in data]}
    head = f'<h4 class="chart-title">{esc(title)}</h4>' if title else ""
    return f'<div class="chart-box">{head}<div class="chart-canvas" data-chart="bar" data-spec="{esc(json_dumps(spec))}"></div>{_chart_fallback_table(rows, cols)}</div>'


def chart_pie(title: str, rows: Sequence[Mapping[str, Any]], name_key: str, value_key: str, *, donut: bool = False, columns: Sequence[tuple[str, str]] | None = None) -> str:
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return '<p class="muted">暂无数据</p>'
    cols = columns or [(name_key, name_key), (value_key, value_key)]
    data = [{"name": text(r.get(name_key)), "value": _num(r.get(value_key))} for r in rows]
    spec = {"type": "pie", "donut": donut, "data": data}
    head = f'<h4 class="chart-title">{esc(title)}</h4>' if title else ""
    return f'<div class="chart-box">{head}<div class="chart-canvas" data-chart="pie" data-spec="{esc(json_dumps(spec))}"></div>{_chart_fallback_table(rows, cols)}</div>'


def chart_gauge(title: str, value: float, *, level: str = "", max_val: float = 100.0) -> str:
    spec = {"type": "gauge", "value": _num(value), "max": max_val, "level": level}
    return f'<div class="chart-box chart-box-gauge"><div class="chart-canvas" data-chart="gauge" data-spec="{esc(json_dumps(spec))}"></div></div>'


def chart_radar(title: str, indicators: Sequence[Mapping[str, Any]], series: Sequence[Mapping[str, Any]]) -> str:
    """indicators: [{name, max}], series: [{name, value:[...]}]"""
    spec = {"type": "radar", "indicators": [{"name": i.get("name", ""), "max": _num(i.get("max", 100))} for i in indicators], "series": [{"name": s.get("name", ""), "value": [_num(v) for v in (s.get("value") or [])]} for s in series]}
    return f'<div class="chart-box"><div class="chart-canvas" data-chart="radar" data-spec="{esc(json_dumps(spec))}"></div></div>'


# --------------------------------------------------------------------------- #
# Core analysis rendering — domain-driven via section specs
# --------------------------------------------------------------------------- #

def _render_one_section(core: Mapping[str, Any], spec: Mapping[str, Any]) -> str:
    """Render a single section spec into HTML (without pairing). Returns '' if empty."""
    key = spec.get("key")
    body = core.get(key)
    kind = spec.get("kind")
    title_html = f'<h3 class="biz-subsection-title">{esc(spec.get("title", ""))}</h3>'
    # Replace " N " in note with actual row count when body is a list
    note_text = spec.get("note", "")
    if note_text:
        if isinstance(body, list) and len(body) > 0:
            note_text = note_text.replace("展示前 N 条", f"展示前 {len(body)} 条")
            note_text = note_text.replace("展示前若干条", f"展示前 {len(body)} 条")
            note_text = note_text.replace("展示前 N 个", f"展示前 {len(body)} 个")
            note_text = note_text.replace("展示前 N 家", f"展示前 {len(body)} 家")
    note = f'<p class="biz-section-note">{esc(note_text)}</p>' if note_text else ""

    if kind == "text":
        if not compact(body):
            return ""
        return f'{title_html}<p class="biz-summary">{esc(compact(body, limit=1500))}</p>'
    elif kind == "tags":
        joined = compact(body, limit=400)
        if not joined:
            return ""
        return f'{title_html}<div class="tag-row">{esc(joined)}</div>'
    elif kind == "kv":
        if not isinstance(body, dict) or not body:
            return ""
        return f'{title_html}{render_info_list(body)}'
    elif kind in ("line", "bar", "pie", "donut", "multi_line"):
        rows = [r for r in as_list(body) if isinstance(r, dict)]
        if not rows:
            return ""
        ch = spec.get("chart") or {}
        cols = spec.get("columns") or [(k, k) for k in rows[0].keys()]
        chart_html = ""
        if kind == "line":
            chart_html = chart_line(spec.get("title", ""), rows, ch.get("x", cols[0][1] if cols else ""), ch.get("y", cols[1][1] if len(cols) > 1 else ""), area=ch.get("area", False), columns=cols)
        elif kind == "multi_line":
            chart_html = chart_multi_line(spec.get("title", ""), rows, ch.get("x", cols[0][1] if cols else ""), ch.get("series", []), area=ch.get("area", False), columns=cols)
        elif kind == "bar":
            chart_html = chart_bar(spec.get("title", ""), rows, ch.get("name", cols[0][1] if cols else ""), ch.get("value", cols[1][1] if len(cols) > 1 else ""), orient=ch.get("orient", "v"), columns=cols)
        elif kind in ("pie", "donut"):
            chart_html = chart_pie(spec.get("title", ""), rows, ch.get("name", cols[0][1] if cols else ""), ch.get("value", cols[1][1] if len(cols) > 1 else ""), donut=(kind == "donut" or bool(ch.get("donut"))), columns=cols)
        return f'{note}{chart_html}'
    elif kind == "gauge":
        if not isinstance(body, dict) or not body:
            return ""
        ch = spec.get("chart") or {}
        val = _num(body.get(ch.get("value_key", "风险评分")))
        lvl = text(body.get(ch.get("level_key", "风险等级")))
        # When paired (pair_with set), skip the info-list so both columns are chart-only and equal height
        info_html = "" if spec.get("pair_with") else render_info_list(body)
        return f'{title_html}{note}{chart_gauge(spec.get("title", ""), val, level=lvl, max_val=ch.get("max", 100))}{info_html}'
    elif kind == "radar":
        ch = spec.get("chart") or {}
        inds = ch.get("indicators", [])
        sers = ch.get("series", [])
        if not inds and isinstance(body, dict):
            inds = body.get("indicators", [])
            sers = body.get("series", [])
        if inds and sers:
            return f'{title_html}{note}{chart_radar(spec.get("title", ""), inds, sers)}'
        return ""
    elif kind == "table" or kind is None:
        rows = [r for r in as_list(body) if isinstance(r, dict)]
        if not rows:
            return ""
        columns = spec.get("columns") or [(k, k) for k in rows[0].keys()]
        return f'{title_html}{note}{render_table(rows, columns)}'
    return ""


def render_core_analysis_html(core: Mapping[str, Any], sections: Sequence[Mapping[str, Any]]) -> str:
    """Render section specs. Supports ``pair_with`` to place two lightweight
    sections (e.g. gauge + radar) side-by-side in a two-column layout, avoiding
    large whitespace from single-chart sections.
    """
    blocks: list[str] = []
    skip_keys: set[str] = set()
    for i, spec in enumerate(sections):
        key = spec.get("key")
        if key in skip_keys:
            continue
        # Check if this section wants to pair with the next one
        pair_target = spec.get("pair_with")
        if pair_target:
            # Find the pairing section (usually the next one)
            paired_spec = None
            for s in sections[i + 1:]:
                if s.get("key") == pair_target:
                    paired_spec = s
                    skip_keys.add(pair_target)
                    break
            if paired_spec is not None:
                left = _render_one_section(core, spec)
                right = _render_one_section(core, paired_spec)
                if left and right:
                    blocks.append(f'<div class="biz-pair"><div>{left}</div><div>{right}</div></div>')
                elif left:
                    blocks.append(left)
                elif right:
                    blocks.append(right)
                continue
        html = _render_one_section(core, spec)
        if html:
            blocks.append(html)
    return "\n".join(blocks) if blocks else '<p class="muted">暂无核心分析数据</p>'


# --------------------------------------------------------------------------- #
# Section catalogue (domain adapter) — overridden per skill via get_sections
# --------------------------------------------------------------------------- #

# Per-skill section catalogue. Empty here: this skill drives sections entirely
# via core_analysis.sections in compose_report.py, with a generic heuristic
# fallback below (list-of-dict -> table, non-empty string -> text).
SECTION_CATALOGUE: List[Dict[str, Any]] = []

# Map internal caliber keys to reader-facing Chinese labels, so raw English
# field names (match_target / match_type / data_scope / limit) never leak into
# the rendered report.
CALIBER_LABELS = {
    "match_target": "匹配对象",
    "match_type": "匹配方式",
    "data_scope": "数据范围",
    "limit": "局限说明",
}


def get_sections(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return core_analysis section specs derived from the payload.

    If `core_analysis.sections` is provided, use it. Otherwise use this skill's
    SECTION_CATALOGUE. Fallback heuristic: each list-of-dict key becomes a
    table; each non-empty string becomes a text section.
    """
    core = data.get("core_analysis") or {}
    if isinstance(core, dict) and isinstance(core.get("sections"), list):
        return core["sections"]
    if SECTION_CATALOGUE:
        return SECTION_CATALOGUE
    # Fallback: derive sections from core keys. Use a title map so section
    # headers are Chinese, not raw English snake_case keys.
    _TITLE_MAP = {
        "enterprise_base": "企业基本信息", "identity_tags": "身份标签",
        "description": "企业简介", "business": "经营范围", "tags": "标签",
        "holders": "股东信息", "investments": "对外投资",
        "branches": "分支机构", "key_persons": "主要人员",
        "shareholder_top": "股东持股排行", "shareholding_type": "股东类型分布",
        "shareholder_entity": "股东性质分布",
    }
    sections = []
    for key, value in core.items():
        if key == "sections":
            continue
        title = _TITLE_MAP.get(key, key.replace("_", " ").title())
        if isinstance(value, list) and value and isinstance(value[0], dict):
            sections.append({"key": key, "title": title, "kind": "table"})
        elif isinstance(value, str) and value.strip():
            sections.append({"key": key, "title": title, "kind": "text"})
        elif isinstance(value, list) and value:
            sections.append({"key": key, "title": title, "kind": "table"})
    return sections



# --------------------------------------------------------------------------- #
# Professional terms glossary
# --------------------------------------------------------------------------- #

_GLOSSARY = {
    "CR3": "行业集中度指标（Concentration Ratio 3），指排名前 3 的类别合计占总量的百分比。CR3 越高说明分布越集中，反之越分散。常用于衡量城市、品牌、产品类型等的集中程度。",
    "CR2": "行业集中度指标（Concentration Ratio 2），指排名前 2 的类别合计占总量的百分比。含义同 CR3，但仅统计前 2 名。",
    "CR5": "行业集中度指标（Concentration Ratio 5），指排名前 5 的类别合计占总量的百分比。",
    "同比": "与上一年度同一时期对比的变化率。例如 2024 年同比增长率 = (2024 年值 - 2023 年值) / 2023 年值 * 100%。",
    "环比": "与紧邻的上一时期（上月/上季）对比的变化率。例如 7 月环比 = (7 月值 - 6 月值) / 6 月值 * 100%。",
    "分位": "统计学概念，指某数值在全体样本中的相对位置。如「前 1.4% 分位」表示该数值高于 98.6% 的样本。",
    "SKU": "库存量单位（Stock Keeping Unit），商品的最小分类单元，每个 SKU 对应一种独立的商品规格。",
}


def _detect_glossary_terms(report: Mapping[str, Any]) -> list:
    """Scan report text for professional terms. Returns [(term, definition), ...]."""
    parts = [str(report.get("abstract", "")), str(report.get("summary", ""))]
    for item in as_list(report.get("executive_summary")):
        parts.append(str(item))
    for ins in as_list(report.get("insights")):
        if isinstance(ins, dict):
            parts.append(str(ins.get("evidence", "")))
            parts.append(str(ins.get("interpretation", "")))
            parts.append(str(ins.get("feature", "")))
    for m in as_list(report.get("metrics")):
        if isinstance(m, dict):
            parts.append(str(m.get("label", "")))
            parts.append(str(m.get("hint", "")))
            parts.append(str(m.get("delta", "")))
    core = report.get("core_analysis", {})
    if isinstance(core, dict):
        for sec in as_list(core.get("sections")):
            if isinstance(sec, dict):
                parts.append(str(sec.get("note", "")))
                parts.append(str(sec.get("summary", "")))
    combined = " ".join(parts)
    found = []
    for term, definition in _GLOSSARY.items():
        if term in combined:
            found.append((term, definition))
    return found


# --------------------------------------------------------------------------- #
# HTML document
# --------------------------------------------------------------------------- #

def render_html(data: Dict[str, Any], *, sections: Sequence[Mapping[str, Any]] | None = None) -> str:
    title = infer_title(data)
    banner = infer_banner(data)
    generated_at = compact(data.get("data_source", {}).get("generated_at") or dt.datetime.now().astimezone().isoformat(timespec="seconds"))
    try:
        _gd = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        generated_at_cn = f"{_gd.year}年{_gd.month:02d}月{_gd.day:02d}日"
    except Exception:
        generated_at_cn = generated_at[:10] if len(generated_at) >= 10 else generated_at
    subject = data.get("subject") or {}
    abstract = compact(data.get("abstract") or data.get("summary") or "")
    exec_summary = data.get("executive_summary") or []
    metrics = data.get("metrics") or []
    caliber = data.get("caliber") or {}
    core = data.get("core_analysis") or {}
    records = data.get("representative_records") or []
    insights = data.get("insights") or []
    sections = sections or get_sections(data)

    toc = ["报告摘要", "查询对象与口径", "数据总览", "核心分析", "代表性记录", "特征与洞察"]
    toc_html = "".join(f"<li><span>{esc(item)}</span></li>" for item in toc)

    scope_items = []
    for key in ("match_target", "match_type", "data_scope", "limit"):
        if caliber.get(key):
            scope_items.append((CALIBER_LABELS.get(key, key), caliber[key]))
    scope_html = "".join(
        f'<div class="biz-scope-item"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'
        for label, value in scope_items
    ) or '<div class="biz-scope-item"><span>说明</span><strong>见正文口径章节</strong></div>'

    exec_html = "".join(f"<li>{esc(line)}</li>" for line in exec_summary) if exec_summary else ""
    # Build cover findings from insights (top 4) to fill the cover page
    cover_insights = insights[:4] if insights else []
    findings_html = ""
    if cover_insights:
        cards = []
        for ins in cover_insights:
            feature = esc(ins.get("feature", ""))
            evidence = esc(ins.get("evidence", ""))
            interpretation = esc(compact(ins.get("interpretation", ""), limit=80))
            text = evidence if evidence else interpretation
            if feature and text:
                cards.append(f'<div class="finding-card"><p class="f-label">{feature}</p><p class="f-text">{text}</p></div>')
        if cards:
            findings_html = f'<div class="cover-findings"><h3 class="cover-findings-title">核心发现</h3><div class="cover-findings-grid">{"".join(cards)}</div></div>'
    # --- Cover page enrichment: dimensions, scope, supplementary metrics ---
    import re as _re_sup

    # 1) Analysis dimensions from section titles
    _dim_titles = [s.get("title", "") for s in sections if s.get("title")]
    _dim_tags = "".join(f'<span class="dim-tag">{esc(t)}</span>' for t in _dim_titles) if _dim_titles else ""
    dimensions_html = ""
    if _dim_tags:
        dimensions_html = f'<div class="cover-dimensions"><span class="dim-label">分析维度</span><div class="dim-tags">{_dim_tags}</div></div>'

    # 2) Data scope info bar from caliber
    _scope_parts = []
    if caliber.get("products"):
        _scope_parts.append(("数据产品", "、".join(caliber["products"])))
    if caliber.get("data_scope"):
        _scope_parts.append(("覆盖范围", str(caliber["data_scope"])[:80]))
    scope_bar_html = ""
    if _scope_parts:
        _scope_items = "".join(f'<span class="scope-item"><em>{esc(l)}</em>{esc(v)}</span>' for l, v in _scope_parts)
        scope_bar_html = f'<div class="cover-scope-bar">{_scope_items}</div>'

    # 3) Supplementary metrics from insight evidence (only when sparse)
    _valid_metric_count = len([m for m in metrics if m.get("value", "-") != "-"])
    if _valid_metric_count < 6 and insights:
        _existing_lower = set()
        _existing_vals = set()
        for m in metrics:
            _existing_lower.add(m.get("label", "").lower())
            v = str(m.get("value", ""))
            _existing_vals.add(v.replace(",", "").replace(" ", ""))
        _supplementary = []
        for ins in insights:
            feature = ins.get("feature", "")
            evidence = ins.get("evidence", "")
            if not feature or not evidence:
                continue
            _feat_lower = feature.lower()
            if any(_feat_lower in lbl or lbl in _feat_lower for lbl in _existing_lower):
                continue
            _val = None
            # Try percentage first (e.g., "占比约 31%", "合计 62%（CR3）")
            _pct_match = _re_sup.search(r'(\d+(?:\.\d+)?)\s*%', evidence)
            if _pct_match:
                _val = f"{_pct_match.group(1)}%"
            else:
                _num_match = _re_sup.search(r'(\d[\d,]*(?:\.\d+)?)\s*(件|个|家|条|人|轮|次|项|场)', evidence)
                if _num_match:
                    _raw = _num_match.group(1).replace(",", "")
                    try:
                        _num = float(_raw)
                        if _num == int(_num):
                            _num = int(_num)
                        if isinstance(_num, int) and _num >= 1000:
                            _val = f"{_num:,}"
                        elif isinstance(_num, float):
                            _val = f"{_num:.1f}"
                        else:
                            _val = str(_num)
                        if _num_match.group(2):
                            _val += f" {_num_match.group(2)}"
                    except ValueError:
                        pass
            if not _val:
                continue
            # Skip if value duplicates an existing metric value
            _val_clean = _val.replace(",", "").replace(" ", "").replace("%", "")
            if _val_clean in _existing_vals:
                continue
            _short_label = feature[:10] if len(feature) > 10 else feature
            _supplementary.append({"label": _short_label, "value": _val, "hint": ""})
            _existing_lower.add(_feat_lower)
            _existing_vals.add(_val_clean)
            if len(_supplementary) >= 4:
                break
        if _supplementary:
            metrics = list(metrics) + _supplementary



    core_html = render_core_analysis_html(core, sections)

    # Build glossary section from detected professional terms
    _glossary_terms = _detect_glossary_terms(data)
    glossary_html = ""
    if _glossary_terms:
        _glossary_rows = "".join(
            f'<div class="glossary-row"><span class="glossary-term">{esc(t)}</span><span class="glossary-def">{esc(d)}</span></div>'
            for t, d in _glossary_terms
        )
        glossary_html = (
            f'<section class="report-page biz-section">'
            f'<div class="report-topbar"><div class="report-stripe"></div>'
            f'<div class="report-banner">{esc(banner)}</div></div>'
            f'<div class="biz-section-head"><div><h2>名词解释</h2>'
            f'<p class="biz-section-note">报告中涉及的专业术语与统计指标说明。</p></div>'
            f'<span class="biz-tag">Glossary</span></div>'
            f'<div class="glossary-list">{_glossary_rows}</div>'
            f'</section>'
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>{esc(title)}</title>
  <style>
    :root {{ --bg:#eef1f5; --card:#ffffff; --text:#1f2937; --muted:#64748b; --line:#d8dee8; --blue:#003b71; --deep:#003b71; --red:#7f1d1d; --gold:#d97706; --stripe:#666; }}
    * {{ box-sizing:border-box; letter-spacing:0 !important; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Songti SC","STSong","Noto Serif CJK SC","Source Han Serif SC","SimSun",serif; line-height:1.78; }}
    .research-doc {{ width:min(1120px,100%); margin:0 auto 42px; padding:0 22px; }}
    .report-page {{ position:relative; width:min(1080px,calc(100vw - 32px)); margin:28px auto; background:#fff; border:1px solid #a8adb5; box-shadow:0 18px 44px rgba(15,23,42,.13); }}
    .report-topbar {{ display:flex; align-items:stretch; height:54px; border-bottom:1px solid #333; }}
    .report-stripe {{ flex:1; background:repeating-linear-gradient(0deg,#575757 0,#575757 2px,#747474 2px,#747474 4px); }}
    .report-banner {{ width:420px; display:flex; align-items:center; justify-content:flex-end; padding:0 24px; color:#fff; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; font-weight:800; letter-spacing:.08em; background:linear-gradient(135deg,#0b4c84,#0284c7 48%,#0b2f55); }}
    .cover-grid {{ display:grid; grid-template-columns:330px minmax(0,1fr); min-height:860px; }}
    .cover-side {{ padding:86px 34px 96px; border-right:0; position:relative; }}
    .cover-side-title {{ color:var(--red); font-size:32px; font-weight:800; letter-spacing:.08em; margin:0 0 12px; }}
    .cover-date {{ margin:0 0 60px; color:#111827; font-size:17px; font-weight:700; }}
    .toc-title,.scope-title {{ margin:0 0 12px; color:#111827; font-size:19px; font-weight:800; border-bottom:2px solid var(--red); padding-bottom:8px; }}
    .toc-list {{ list-style:none; padding:0; margin:0 0 56px; }}
    .toc-list li {{ border-bottom:1px solid #e5e7eb; padding:9px 0; color:#475569; font-size:14px; }}
    .toc-list span {{ display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .cover-brand {{ position:absolute; left:38px; bottom:38px; color:#7a7a7a; font-size:24px; font-weight:900; letter-spacing:.02em; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .cover-main {{ padding:72px 54px 54px 34px; }}
    .report-kicker {{ margin:0 0 16px; color:var(--deep); font-size:16px; font-weight:800; letter-spacing:.16em; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    h1 {{ margin:0 0 20px; color:#0b3768; font-size:36px; line-height:1.25; letter-spacing:-.03em; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .report-lead {{ margin:0 0 22px; color:#0b3768; font-size:19px; line-height:1.85; font-weight:800; }}
    .abstract-box {{ border-left:5px solid var(--gold); background:#fff8eb; padding:16px 18px; color:#9a4b00; font-size:17px; line-height:1.8; font-style:italic; margin:22px 0 24px; }}
    .biz-metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1px; margin:22px 0; background:#d6dee9; border:1px solid #d6dee9; }}
    .biz-metric {{ background:#fff; padding:16px 14px; display:flex; flex-direction:column; min-height:88px; }}
    .biz-metric-empty {{ background:#f8fafc; visibility:hidden; }}
    .biz-metric .m-name {{ color:#64748b; font-size:12px; font-weight:700; line-height:1.2; margin-bottom:4px; }}
    .biz-metric .m-tag {{ font-size:11px; font-weight:800; line-height:1; margin-bottom:10px; display:block; min-height:11px; }}
    .biz-metric .m-tag.t-up {{ color:#16a34a; }}
    .biz-metric .m-tag.t-down {{ color:#dc2626; }}
    .biz-metric .m-tag.t-neutral {{ color:#6366f1; }}
    .biz-metric .m-value {{ color:#0b3768; font-size:26px; line-height:1.1; font-weight:900; letter-spacing:-.02em; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; margin-top:auto; }}
    .biz-metric .m-value .m-tag.t-up {{ color:#16a34a; }}
    .biz-metric .m-value .m-tag.t-down {{ color:#dc2626; }}
    .biz-metric .m-value .m-tag.t-neutral {{ color:#6366f1; }}
    .exec-list {{ list-style:none; padding:0; margin:18px 0 0; }}
    .exec-list li {{ position:relative; padding:8px 0 8px 22px; color:#334155; font-size:14px; line-height:1.7; border-bottom:1px solid #eef2f7; }}
    .exec-list li:last-child {{ border-bottom:0; }}
    .exec-list li::before {{ content:""; position:absolute; left:0; top:14px; width:8px; height:8px; background:#0b5ca8; border-radius:50%; }}
    .cover-findings {{ margin:20px 0 0; }}
    .cover-findings-title {{ margin:0 0 12px; color:#0b3768; font-size:16px; font-weight:800; border-bottom:2px solid #0b5ca8; padding-bottom:6px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .cover-findings-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    .finding-card {{ border:1px solid #d6e3f0; border-left:4px solid #0b5ca8; background:#f8fbff; padding:10px 12px; }}
    .finding-card .f-label {{ color:#0b5ca8; font-size:12px; font-weight:800; margin:0 0 4px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .finding-card .f-text {{ color:#334155; font-size:12.5px; line-height:1.6; margin:0; }}
    .cover-dimensions {{ margin:18px 0 0; display:flex; align-items:flex-start; gap:8px; }}
    .cover-dimensions .dim-label {{ flex-shrink:0; color:#0b3768; font-size:13px; font-weight:800; line-height:1.9; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .cover-dimensions .dim-tags {{ display:flex; flex-wrap:wrap; gap:4px; }}
    .dim-tag {{ display:inline-block; background:#eaf4ff; color:#0b5ca8; padding:3px 10px; font-size:11.5px; border-radius:12px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; white-space:nowrap; }}
    .cover-scope-bar {{ margin:14px 0 0; padding:10px 14px; background:#f8fafc; border-left:4px solid #0b5ca8; display:flex; flex-direction:column; gap:4px; }}
    .cover-scope-bar .scope-item {{ font-size:12px; color:#334155; line-height:1.6; }}
    .cover-scope-bar .scope-item em {{ font-style:normal; color:#0b5ca8; font-weight:700; margin-right:6px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .report-page.biz-section {{ padding:0 30px 34px; }}
    .report-page.biz-section > .report-topbar {{ margin:0 -30px 30px; }}
    .biz-section-head {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:18px; }}
    .biz-section h2 {{ margin:0; color:#0b3768; font-size:26px; letter-spacing:.03em; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .biz-section-note {{ margin:6px 0 0; color:var(--muted); font-size:13px; }}
    .biz-tag {{ background:#eaf4ff; color:#0b3768; padding:5px 10px; font-size:12px; font-weight:800; white-space:nowrap; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .biz-summary {{ font-size:16px; color:#243041; text-align:justify; }}
    .biz-scope {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:18px; }}
    .cover-side .biz-scope {{ grid-template-columns:1fr; }}
    .biz-scope-item {{ border:1px solid #d6dee9; background:#f8fbff; padding:12px; }}
    .biz-scope-item span {{ display:block; color:#64748b; font-size:12px; font-weight:700; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .biz-scope-item strong {{ display:block; margin-top:4px; color:#0b3768; font-size:13px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .info-list {{ border:1px solid #d6dee9; background:#fff; }}
    .info-row {{ display:grid; grid-template-columns:148px minmax(0,1fr); gap:0; align-items:stretch; border-bottom:1px solid #e8edf3; }}
    .info-row:last-child {{ border-bottom:0; }}
    .info-label {{ display:flex; align-items:center; gap:8px; padding:13px 14px; background:#f1f6fb; color:#0b3768; font-size:13px; font-weight:800; border-right:3px solid #0b5ca8; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .info-value {{ padding:13px 16px; color:#334155; font-size:13.5px; line-height:1.78; overflow-wrap:anywhere; }}
    .biz-subsection-title {{ margin:26px 0 12px; padding-left:12px; border-left:4px solid #0b5ca8; color:#0b3768; font-size:18px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .biz-pair {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; align-items:stretch; }}
    .biz-pair > div {{ display:flex; flex-direction:column; }}
    .biz-pair .biz-subsection-title {{ margin-top:0; }}
    .chart-box-gauge {{ width:100%; margin:0 auto; }}
    .chart-box {{ min-height:300px; }}
    .biz-pair .chart-box {{ flex:1; min-height:340px; }}
    .biz-pair .chart-canvas {{ height:300px !important; }}
    .biz-pair .table-wrap {{ flex:1; }}
    .biz-pair .info-list {{ flex:1; }}
    @media (max-width:860px) {{ .biz-pair {{ grid-template-columns:1fr; }} }}
    .tag-row {{ background:#f8fbff; border:1px solid #d6dee9; padding:14px 16px; color:#0b3768; font-size:14px; line-height:1.8; }}
    .structural-feature-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .structural-feature-card {{ border:1px solid #cbd5e1; background:#fff; padding:16px; }}
    .structural-feature-card h3 {{ margin:0 0 10px; color:#0b3768; font-size:17px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .structural-feature-card p {{ margin:8px 0 0; color:#475569; font-size:13px; line-height:1.7; }}
    .structural-feature-card .structural-evidence {{ border-left:4px solid #d97706; background:#fff8eb; padding:9px 11px; color:#92400e; font-weight:700; }}
    .table-wrap {{ overflow:auto; border:1px solid #0b3768; }}
    table {{ width:100%; border-collapse:collapse; background:white; }}
    th,td {{ padding:12px 13px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:13px; overflow-wrap:anywhere; }}
    th {{ background:#0b3768; color:white; font-weight:800; white-space:nowrap; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    tbody tr:nth-child(even) td {{ background:#dff1fb; }}
    tr:last-child td {{ border-bottom:0; }}
    .source-link {{ color:#0b5ca8; font-weight:800; text-decoration:none; white-space:nowrap; }}
    ul {{ margin:0 0 0 20px; padding:0; }} li {{ margin:7px 0; }}
    .muted {{ color:var(--muted); }}
    footer {{ width:min(1080px,100%); margin:0 auto; padding:0 24px 36px; color:#64748b; font-size:12px; }}
    @media (max-width: 860px) {{ .cover-grid {{ grid-template-columns:1fr; }} .cover-side {{ padding:34px; }} .cover-brand {{ position:static; margin-top:32px; }} .biz-metrics,.biz-scope {{ grid-template-columns:1fr 1fr; }} .table-wrap table {{ min-width:720px; }} .structural-feature-grid {{ grid-template-columns:1fr; }} h1 {{ font-size:30px; }} .report-banner {{ width:55%; }} }}
    @page {{ size:A4; margin:12mm; }}
    @media print {{
      body {{ background:#fff; line-height:1.55; }}
      .report-page {{ width:100%; margin:0; box-shadow:none; break-after:page; }}
      .research-doc {{ width:100%; padding:0; margin:0; }}
      .cover-grid {{ grid-template-columns:190px minmax(0,1fr); min-height:690px; }}
      .cover-side {{ padding:34px 18px 60px; }}
      .cover-side-title {{ font-size:24px; }}
      .cover-date {{ margin-bottom:28px; font-size:13px; }}
      .toc-title,.scope-title {{ font-size:14px; padding-bottom:5px; }}
      .toc-list {{ margin-bottom:24px; }}
      .toc-list li {{ padding:5px 0; font-size:10px; }}
      .cover-brand {{ left:20px; bottom:20px; font-size:16px; }}
      .cover-main {{ padding:38px 28px 28px 22px; }}
      .report-kicker {{ margin-bottom:10px; font-size:11px; }}
      h1 {{ margin-bottom:12px; font-size:27px; }}
      .report-lead {{ margin-bottom:12px; font-size:12px; line-height:1.65; }}
      .abstract-box {{ margin:12px 0 14px; padding:10px 12px; font-size:10px; line-height:1.55; }}
      .biz-metrics {{ gap:6px; margin:12px 0; }}
      .biz-metric {{ padding:8px; }}
      .biz-metric strong {{ font-size:16px; }}
      .biz-metric span {{ margin-top:4px; font-size:8px; }}
      .info-label {{ padding:7px 9px; font-size:9px; border-right-width:2px; }}
      .info-value {{ padding:7px 9px; font-size:9.5px; line-height:1.5; }}
      .info-row {{ grid-template-columns:108px minmax(0,1fr); }}
      .report-page.biz-section {{ padding:0 18px 22px; }}
      .report-page.biz-section > .report-topbar {{ margin:0 -18px 18px; }}
      .biz-section-head {{ margin-bottom:12px; }}
      .biz-section h2 {{ font-size:20px; }}
      .biz-section-note,.biz-tag {{ font-size:9px; }}
      .table-wrap {{ overflow:visible; }}
      .table-wrap table {{ min-width:0 !important; }}
      th,td {{ padding:6px 7px; font-size:8.5px; line-height:1.45; }}
      .structural-feature-card,.biz-section {{ break-inside:avoid; }}
      .structural-feature-grid {{ gap:8px; }}
      .structural-feature-card {{ padding:10px; }}
      .structural-feature-card p {{ font-size:9px; line-height:1.45; }}
      footer {{ display:none; }}
    }}
    .chart-box {{ border:1px solid #d6dee9; background:#fff; padding:16px; margin:10px 0 16px; }}
    .chart-box-gauge {{ max-width:380px; }}
    .chart-title {{ margin:0 0 8px; color:#0b3768; font-size:15px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .chart-canvas {{ width:100%; height:300px; }}
    .chart-box-gauge .chart-canvas {{ height:240px; }}
    .chart-data {{ margin-top:10px; }}
    .chart-data summary {{ cursor:pointer; color:#0b5ca8; font-size:12px; font-weight:700; padding:4px 0; }}
    .metric-rich {{ border:1px solid #cbd5e1; background:#f8fbff; padding:14px; position:relative; }}
    .metric-rich strong {{ display:block; color:#0b3768; font-size:25px; line-height:1; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .metric-rich .m-label {{ display:block; margin-top:7px; color:#475569; font-size:12px; font-weight:800; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .metric-rich .m-delta {{ display:inline-block; margin-left:6px; font-size:12px; font-weight:800; }}
    .metric-rich .m-up {{ color:#dc2626; }}
    .metric-rich .m-down {{ color:#059669; }}
    @media print {{
      .chart-box {{ break-inside:avoid; padding:10px; }}
      .chart-data {{ display:none; }}
    }}
    .glossary-list {{ border:1px solid #d6dee9; background:#fff; }}
    .glossary-row {{ display:grid; grid-template-columns:130px minmax(0,1fr); gap:0; align-items:stretch; border-bottom:1px solid #e8edf3; }}
    .glossary-row:last-child {{ border-bottom:0; }}
    .glossary-term {{ display:flex; align-items:flex-start; padding:12px 14px; background:#f1f6fb; color:#0b5ca8; font-size:13px; font-weight:800; border-right:3px solid #0b5ca8; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    .glossary-def {{ padding:12px 16px; color:#334155; font-size:13px; line-height:1.7; }}
  </style>
  <script>{_echarts_inline_or_cdn()}</script>
  <script>{_HANDAAS_CHART_JS}</script>
</head>
<body>
  <article class="report-page">
    <div class="report-topbar"><div class="report-stripe"></div><div class="report-banner">{esc(banner)}</div></div>
    <div class="cover-grid">
      <aside class="cover-side">
        <h2 class="cover-side-title">{esc(banner)}</h2>
        <p class="cover-date">{esc(generated_at_cn)}</p>
        <h3 class="toc-title">目录</h3>
        <ol class="toc-list">{toc_html}</ol>
        <h3 class="scope-title">报告口径</h3>
        <div class="biz-scope">{scope_html}</div>
      </aside>
      <section class="cover-main">
        <p class="report-kicker">RECRUITMENT DATA RESEARCH</p>
        <h1>{esc(title)}</h1>
        <p class="report-lead">{esc(compact(abstract, limit=400) or "本报告基于商标公开数据，对目标商标的核心维度进行结构化呈现。")}</p>
        <div class="abstract-box">报告涵盖查询对象、数据总览、核心分析、代表性记录与结构洞察，所有数据均标注口径与来源。</div>
        {render_metrics(metrics)}
        {'<ul class="exec-list">' + exec_html + '</ul>' if exec_html else ''}
        {findings_html}
        {dimensions_html}
        {scope_bar_html}
      </section>
    </div>
  </article>
  <main class="research-doc">
    <section class="report-page biz-section"><div class="report-topbar"><div class="report-stripe"></div><div class="report-banner">{esc(banner)}</div></div><div class="biz-section-head"><div><h2>报告摘要</h2><p class="biz-section-note">概述分析对象、数据覆盖范围与核心发现。</p></div><span class="biz-tag">Summary</span></div><p class="biz-summary">{esc(abstract or "暂无摘要。")}</p></section>
    <section class="report-page biz-section"><div class="report-topbar"><div class="report-stripe"></div><div class="report-banner">{esc(banner)}</div></div><div class="biz-section-head"><div><h2>查询对象与口径</h2><p class="biz-section-note">说明匹配对象、匹配方式与数据范围。</p></div><span class="biz-tag">Caliber</span></div>{render_info_list({'匹配对象': caliber.get('match_target') or subject.get('enterprise') or '-', '匹配方式': caliber.get('match_type') or '-', '数据范围': caliber.get('data_scope') or '-', '局限说明': caliber.get('limit') or '-'})}</section>
    <section class="report-page biz-section"><div class="report-topbar"><div class="report-stripe"></div><div class="report-banner">{esc(banner)}</div></div><div class="biz-section-head"><div><h2>数据总览</h2><p class="biz-section-note">关键指标一览。</p></div><span class="biz-tag">Metrics</span></div>{render_metrics(metrics) or '<p class="muted">暂无指标</p>'}</section>
    <section class="report-page biz-section"><div class="report-topbar"><div class="report-stripe"></div><div class="report-banner">{esc(banner)}</div></div><div class="biz-section-head"><div><h2>核心分析</h2><p class="biz-section-note">按维度展开目标核心数据与结构化明细。</p></div><span class="biz-tag">Analysis</span></div>{core_html}</section>
    <section class="report-page biz-section"><div class="report-topbar"><div class="report-stripe"></div><div class="report-banner">{esc(banner)}</div></div><div class="biz-section-head"><div><h2>代表性记录</h2><p class="biz-section-note">关键明细记录 Top N。</p></div><span class="biz-tag">Records</span></div>{render_records(records)}</section>
    <section class="report-page biz-section"><div class="report-topbar"><div class="report-stripe"></div><div class="report-banner">{esc(banner)}</div></div><div class="biz-section-head"><div><h2>特征与洞察</h2><p class="biz-section-note">基于数据的结构化解读。</p></div><span class="biz-tag">Insights</span></div>{render_insights(insights)}</section>
    {glossary_html}
  </main>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Markdown document
# --------------------------------------------------------------------------- #

def md_table(rows: Sequence[Any], columns: Sequence[tuple[str, str]] | None = None) -> str:
    rows = [r for r in rows if isinstance(r, dict)] if rows else []
    if not rows:
        return "_暂无数据_\n"
    if not columns:
        columns = [(str(k), str(k)) for k in rows[0].keys()]
    head = "| " + " | ".join(label for _, label in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(text(row.get(key, "")) or "-" for key, _ in columns) + " |")
    return "\n".join([head, sep, *body]) + "\n"


def render_markdown(data: Dict[str, Any]) -> str:
    title = infer_title(data)
    subject = data.get("subject") or {}
    metrics = data.get("metrics") or []
    caliber = data.get("caliber") or {}
    core = data.get("core_analysis") or {}
    records = data.get("representative_records") or []
    insights = data.get("insights") or []
    ds = data.get("data_source") or {}
    sections = get_sections(data)

    lines: List[str] = []
    lines.append(f"# {title}\n")
    lines.append(f"> {compact(data.get('abstract') or data.get('summary') or '')}\n")
    if ds.get("generated_at"):
        lines.append(f"_生成时间：{ds.get('generated_at')}_\n")

    lines.append("## 一、查询对象与口径\n")
    lines.append(f"- 匹配对象：{caliber.get('match_target') or subject.get('enterprise') or '-'}")
    lines.append(f"- 匹配方式：{caliber.get('match_type') or '-'}")
    lines.append(f"- 数据范围：{caliber.get('data_scope') or '-'}")
    lines.append(f"- 局限说明：{caliber.get('limit') or '-'}\n")

    if metrics:
        lines.append("## 二、数据总览\n")
        lines.append("| 指标 | 数值 | 说明 |")
        lines.append("| --- | --- | --- |")
        for m in metrics:
            if isinstance(m, dict):
                lines.append(f"| {m.get('label','')} | {m.get('value','-')} | {m.get('hint','')} |")
        lines.append("")

    lines.append("## 三、核心分析\n")
    for spec in sections:
        key = spec.get("key")
        body = core.get(key)
        kind = spec.get("kind")
        if kind == "text":
            if compact(body):
                lines.append(f"### {spec.get('title', key)}\n")
                lines.append(f"{compact(body, limit=1500)}\n")
        elif kind == "tags":
            if compact(body):
                lines.append(f"### {spec.get('title', key)}\n")
                lines.append(f"{compact(body, limit=400)}\n")
        elif kind == "kv" and isinstance(body, dict) and body:
            lines.append(f"### {spec.get('title', key)}\n")
            lines.append("| 字段 | 内容 |")
            lines.append("| --- | --- |")
            for k, v in body.items():
                if v not in (None, "", [], {}):
                    lines.append(f"| {k} | {text(v)} |")
            lines.append("")
        elif kind == "table":
            rows = [r for r in as_list(body) if isinstance(r, dict)]
            if rows:
                lines.append(f"### {spec.get('title', key)}\n")
                if spec.get("note"):
                    lines.append(f"_{spec['note']}_\n")
                cols = spec.get("columns") or [(k, k) for k in rows[0].keys()]
                lines.append(md_table(rows, cols))

    if records:
        lines.append("## 四、代表性记录\n")
        recs = [r for r in records if isinstance(r, dict)]
        if recs:
            cols = [(k, k) for k in recs[0].keys()]
            lines.append(md_table(recs, cols))

    if insights:
        lines.append("## 五、特征与洞察\n")
        for item in insights:
            if isinstance(item, dict):
                lines.append(f"### {item.get('feature','')}")
                lines.append(f"- 证据：{item.get('evidence','')}")
                lines.append(f"- 解读：{item.get('interpretation','')}\n")

    lines.append("## 六、数据口径与来源\n")
    lines.append(f"- 数据来源：{ds.get('mcp_server','-')}")
    lines.append(f"- 生成时间：{ds.get('generated_at','-')}")
    lines.append(f"- 模式：{'Dry-run 样例' if ds.get('dry_run') else '真实查询'}")
    return "\n".join(lines)


def build_payload(*args: Any, **kwargs: Any) -> Dict[str, Any]:  # pragma: no cover (placeholder for import compat)
    return {}


def html_to_pdf(html_str: str, pdf_path: str) -> None:
    """Convert HTML string to PDF using Playwright headless Chromium."""
    import tempfile
    tmp = pathlib.Path(tempfile.mktemp(suffix=".html"))
    try:
        tmp.write_text(html_str, encoding="utf-8")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{tmp.resolve()}", wait_until="networkidle")
            # Wait for ECharts SVG rendering to complete
            page.wait_for_timeout(2000)
            # Force all ECharts instances to resize before PDF capture
            page.evaluate("window.__echarts_resize_all && window.__echarts_resize_all()")
            page.wait_for_timeout(500)
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
            )
            browser.close()
    except ImportError:
        print("⚠️  PDF 转换需要 Playwright (pip install playwright && playwright install chromium)", file=sys.stderr)
        raise
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a HandaaS data report as HTML, Markdown or PDF.")
    parser.add_argument("--input", help="JSON report path; reads stdin when omitted.")
    parser.add_argument("--output", help="Output path; .html, .md or .pdf decides format.")
    parser.add_argument("--title", help="Override report title.")
    args = parser.parse_args()

    data = load_payload(args.input)
    if args.title:
        data["title"] = args.title
    out = pathlib.Path(args.output).expanduser() if args.output else None
    suffix = out.suffix.lower() if out else ""
    if not out:
        print(render_markdown(data))
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    if suffix in (".html", ".htm"):
        out.write_text(render_html(data), encoding="utf-8")
    elif suffix == ".pdf":
        html_to_pdf(render_html(data), str(out))
    else:
        out.write_text(render_markdown(data), encoding="utf-8")
    print_json_like({"ok": True, "output": str(out)})


def print_json_like(value: Dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
