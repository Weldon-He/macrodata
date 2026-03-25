# -*- coding: utf-8 -*-
"""
宏观指标监控仪表盘
"""

import streamlit as st
import os
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime
from typing import Optional

# ====================== 基础配置 ======================
st.set_page_config(page_title="宏观指标监控仪表盘", layout="wide")

# ====================== 读取 API Key ======================
fred_api_key = os.getenv("FRED_API_KEY") or st.secrets.get("FRED_API_KEY", "")
if not fred_api_key:
    st.error("❌ 未配置 FRED_API_KEY！请在 Streamlit Secrets 或环境变量中配置")
    st.stop()

oilprice_api_key = os.getenv("OILPRICE_API_KEY") or st.secrets.get("OILPRICE_API_KEY", "")
if not oilprice_api_key:
    st.warning("⚠️ 未配置 OILPRICE_API_KEY，WTI / Brent 原油价格将无法加载")

# ====================== 定义指标 ======================
INDICATORS = {
    # FRED 指标
    "T5YIE": {
        "name": "5年期盈亏平衡通胀率",
        "desc": "反映市场对5年通胀的预期",
        "color": "#1f77b4",
        "source": "fred",
    },
    "T5YIFR": {
        "name": "5年期远期通胀预期",
        "desc": "更前瞻的通胀预期指标",
        "color": "#ff7f0e",
        "source": "fred",
    },
    "DGS2": {
        "name": "2年期美债收益率",
        "desc": "反映美联储政策预期",
        "color": "#2ca02c",
        "source": "fred",
    },
    "BAMLH0A0HYM2": {
        "name": "高收益债OAS",
        "desc": "信用利差，越高信用风险越大",
        "color": "#d62728",
        "source": "fred",
    },
    "VIXCLS": {
        "name": "VIX恐慌指数",
        "desc": ">30为高恐慌，<20为低恐慌",
        "color": "#9467bd",
        "source": "fred",
    },
    "NFCI": {
        "name": "NFCI",
        "desc": ">0收紧，<0宽松",
        "color": "#8c564b",
        "source": "fred",
    },
    "ICSA": {
        "name": "初请失业金人数",
        "desc": "失业金首次申请数，反映就业情况",
        "color": "#e377c2",
        "source": "fred",
    },
    "SAHMREALTIME": {
        "name": "Sahm衰退指标",
        "desc": ">0.5大概率进入衰退",
        "color": "#7f7f7f",
        "source": "fred",
    },
    "SP500": {"name": "S&P500", "desc": "衡量美国大盘股表现的核心指数", "color": "#17becf", "source": "fred"},
    # OilPriceAPI 指标
    "WTI_OILPRICE": {
        "name": "WTI原油价格（过去30天日频）",
        "desc": "OilPriceAPI：过去30天日频价格",
        "color": "#17becf",
        "source": "oilprice",
        "commodity_code": "WTI_USD",
    },
    "BRENT_OILPRICE": {
        "name": "Brent原油价格（过去30天日频）",
        "desc": "OilPriceAPI：过去30天日频价格",
        "color": "#bcbd22",
        "source": "oilprice",
        "commodity_code": "BRENT_CRUDE_USD",
    },
}

# ====================== FRED API 拉取函数 ======================
def fetch_fred_series(series_id: str, api_key: str, start_date: str = "2018-01-01") -> pd.DataFrame:
    """
    直接调用 FRED API 获取指标数据
    """
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "sort_order": "asc"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if "observations" not in data:
            raise ValueError("FRED API 返回格式异常")
        
        df = pd.DataFrame(data["observations"])
        
        # 数据清洗
        df = df[df["value"] != "."]  # 过滤缺失值
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        
        # 去重、排序、设索引
        df = (
            df[["date", "value"]]
            .dropna()
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .set_index("date")
        )
        
        return df
    
    except Exception as e:
        raise ValueError(f"FRED API 拉取失败: {str(e)}")

# ====================== OilPriceAPI 拉取函数 ======================
def fetch_oilprice_series(commodity_code: str, api_key: str) -> pd.DataFrame:
    """
    拉取 OilPriceAPI 过去30天日频价格
    """
    if not api_key:
        raise ValueError("缺少 OILPRICE_API_KEY")

    headers = {"Authorization": f"Token {api_key}"}
    url = "https://api.oilpriceapi.com/v1/prices/past_month"
    params = {
        "by_code": commodity_code,
        "interval": "1d",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("status") != "success":
            raise ValueError(f"OilPriceAPI 返回异常: {payload}")

        prices = payload.get("data", {}).get("prices", [])
        if not prices:
            raise ValueError(f"{commodity_code} 无返回数据")

        df = pd.DataFrame(prices)
        
        # 数据清洗
        if "created_at" not in df.columns or "price" not in df.columns:
            raise ValueError(f"返回列异常: {list(df.columns)}")

        df["date"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert(None)
        df["value"] = pd.to_numeric(df["price"], errors="coerce")

        df = (
            df[["date", "value"]]
            .dropna()
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .set_index("date")
        )

        return df
    
    except Exception as e:
        raise ValueError(f"OilPriceAPI 拉取失败: {str(e)}")


# ====================== 缓存数据 ======================
@st.cache_data(ttl=3600)  # 1小时缓存
def get_macro_data():
    data_dict = {}

    for code, cfg in INDICATORS.items():
        try:
            if cfg["source"] == "fred":
                df = fetch_fred_series(
                    series_id=code,
                    api_key=fred_api_key,
                    start_date="2018-01-01"
                )
                df.rename(columns={"value": cfg["name"]}, inplace=True)
                data_dict[code] = df
                
            elif cfg["source"] == "oilprice":
                if not oilprice_api_key:
                    data_dict[code] = pd.DataFrame()
                    continue
                df = fetch_oilprice_series(
                    commodity_code=cfg["commodity_code"],
                    api_key=oilprice_api_key,
                )
                df.rename(columns={"value": cfg["name"]}, inplace=True)
                data_dict[code] = df

            else:
                data_dict[code] = pd.DataFrame()

        except Exception as e:
            st.warning(f"⚠️ {cfg['name']} 拉取失败：{e}")
            data_dict[code] = pd.DataFrame()

    return data_dict

# ====================== 数据预处理（合并用于叠加） ======================
def merge_selected_data(selected_codes, data_dict):
    df_list = []
    for code in selected_codes:
        if code in data_dict and not data_dict[code].empty:
            df_list.append(data_dict[code])

    if df_list:
        return pd.concat(df_list, axis=1, join="outer").sort_index()
    return pd.DataFrame()

# ====================== 情景分析辅助函数 ======================
def get_latest_value(data_dict, code: str):
    df = data_dict.get(code)
    if df is None or df.empty:
        return None
    series = df.iloc[:, 0].dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def get_latest_date(data_dict, code: str):
    df = data_dict.get(code)
    if df is None or df.empty:
        return None
    series = df.iloc[:, 0].dropna()
    if series.empty:
        return None
    return pd.to_datetime(series.index[-1])


def get_rolling_mean(data_dict, code: str, window: int = 4):
    df = data_dict.get(code)
    if df is None or df.empty:
        return None
    series = df.iloc[:, 0].dropna().sort_index()
    if series.empty:
        return None
    return float(series.tail(window).mean())


def format_metric_value(code: str, value):
    if value is None:
        return "N/A"
    if code in {"WTI_OILPRICE", "BRENT_OILPRICE"}:
        return f"${value:.2f}"
    if code == "ICSA_4W":
        return f"{int(value):,}"
    if code == "ICSA":
        return f"{int(value):,}"
    return f"{value:.2f}"


def build_current_metrics(data_dict):
    return {
        "WTI_OILPRICE": get_latest_value(data_dict, "WTI_OILPRICE"),
        "BRENT_OILPRICE": get_latest_value(data_dict, "BRENT_OILPRICE"),
        "T5YIE": get_latest_value(data_dict, "T5YIE"),
        "T5YIFR": get_latest_value(data_dict, "T5YIFR"),
        "DGS2": get_latest_value(data_dict, "DGS2"),
        "BAMLH0A0HYM2": get_latest_value(data_dict, "BAMLH0A0HYM2"),
        "VIXCLS": get_latest_value(data_dict, "VIXCLS"),
        "NFCI": get_latest_value(data_dict, "NFCI"),
        "ICSA": get_latest_value(data_dict, "ICSA"),
        "ICSA_4W": get_rolling_mean(data_dict, "ICSA", 4),
        "SAHMREALTIME": get_latest_value(data_dict, "SAHMREALTIME"),
    }


def eval_rule(metric_value, op: str, value=None, low=None, high=None):
    if metric_value is None:
        return False

    if op == ">":
        return metric_value > value
    if op == ">=":
        return metric_value >= value
    if op == "<":
        return metric_value < value
    if op == "<=":
        return metric_value <= value
    if op == "between":
        return low <= metric_value <= high
    return False


def rule_to_text(rule: dict) -> str:
    metric = rule["metric"]
    label = rule.get("label", metric)
    op = rule["op"]

    if op == "between":
        return f"{label} ∈ [{rule['low']}, {rule['high']}]"
    return f"{label} {op} {rule['value']}"


def score_scenario(metrics: dict, scenario: dict):
    matched = []
    missing = []
    conflicts = []

    positive_score = 0
    positive_total = 0

    for rule in scenario["rules"]:
        positive_total += rule["weight"]
        current_value = metrics.get(rule["metric"])
        is_hit = eval_rule(
            current_value,
            rule["op"],
            value=rule.get("value"),
            low=rule.get("low"),
            high=rule.get("high"),
        )
        if is_hit:
            positive_score += rule["weight"]
            matched.append(
                f"{rule_to_text(rule)}（当前 {format_metric_value(rule['metric'], current_value)}）"
            )
        else:
            missing.append(
                f"{rule_to_text(rule)}（当前 {format_metric_value(rule['metric'], current_value)}）"
            )

    penalty = 0
    for rule in scenario.get("anti_rules", []):
        current_value = metrics.get(rule["metric"])
        is_hit = eval_rule(
            current_value,
            rule["op"],
            value=rule.get("value"),
            low=rule.get("low"),
            high=rule.get("high"),
        )
        if is_hit:
            penalty += abs(rule["weight"])
            conflicts.append(
                f"{rule_to_text(rule)}（当前 {format_metric_value(rule['metric'], current_value)}）"
            )

    hard_trigger_hit = False
    for trigger_group in scenario.get("hard_triggers", []):
        if all(
            eval_rule(
                metrics.get(rule["metric"]),
                rule["op"],
                value=rule.get("value"),
                low=rule.get("low"),
                high=rule.get("high"),
            )
            for rule in trigger_group
        ):
            hard_trigger_hit = True
            break

    raw_score = positive_score - penalty
    if hard_trigger_hit:
        raw_score += scenario.get("hard_bonus", 0)

    max_score = positive_total + scenario.get("hard_bonus", 0)
    ratio = 0 if max_score == 0 else max(0, min(1, raw_score / max_score))

    return {
        "key": scenario["key"],
        "label": scenario["label"],
        "color": scenario["color"],
        "summary": scenario["summary"],
        "score": round(raw_score, 2),
        "max_score": round(max_score, 2),
        "ratio": ratio,
        "matched": matched,
        "missing": missing,
        "conflicts": conflicts,
        "hard_trigger_hit": hard_trigger_hit,
    }


def compute_confidence(sorted_results):
    if not sorted_results:
        return 0
    top = sorted_results[0]
    if len(sorted_results) == 1:
        return min(95, max(35, int(top["ratio"] * 100)))

    runner = sorted_results[1]
    gap = max(0, top["ratio"] - runner["ratio"])
    confidence = int(top["ratio"] * 75 + gap * 80)
    return min(95, max(35, confidence))


SCENARIOS = [
    {
        "key": "soft_landing",
        "label": "软着陆 / 震荡修复",
        "color": "green",
        "summary": "通胀锚稳定、利率回落、信用未恶化，就业仍稳。",
        "rules": [
            {"metric": "T5YIE", "op": "<=", "value": 2.40, "weight": 2, "label": "T5YIE"},
            {"metric": "T5YIFR", "op": "between", "low": 2.00, "high": 2.40, "weight": 2, "label": "5y5y近似"},
            {"metric": "DGS2", "op": "<", "value": 3.55, "weight": 2, "label": "2年美债"},
            {"metric": "BAMLH0A0HYM2", "op": "<", "value": 4.00, "weight": 2, "label": "HY OAS"},
            {"metric": "VIXCLS", "op": "<", "value": 20, "weight": 1, "label": "VIX"},
            {"metric": "NFCI", "op": "<", "value": 0, "weight": 1, "label": "NFCI"},
            {"metric": "ICSA_4W", "op": "<", "value": 230000, "weight": 1, "label": "初请4周均值"},
            {"metric": "SAHMREALTIME", "op": "<", "value": 0.30, "weight": 2, "label": "Sahm"},
            {"metric": "BRENT_OILPRICE", "op": "<", "value": 95, "weight": 1, "label": "Brent"},
        ],
        "anti_rules": [
            {"metric": "BRENT_OILPRICE", "op": ">", "value": 105, "weight": -2, "label": "Brent"},
            {"metric": "T5YIE", "op": ">", "value": 2.70, "weight": -2, "label": "T5YIE"},
            {"metric": "VIXCLS", "op": ">", "value": 28, "weight": -2, "label": "VIX"},
        ],
        "hard_triggers": [],
        "hard_bonus": 0,
    },
    {
        "key": "near_term_inflation_shock",
        "label": "近端通胀冲击（未衰退）",
        "color": "yellow",
        "summary": "油价与近端通胀预期上行，但长期通胀锚和增长尚未全面恶化。",
        "rules": [
            {"metric": "BRENT_OILPRICE", "op": ">=", "value": 100, "weight": 2, "label": "Brent"},
            {"metric": "T5YIE", "op": ">=", "value": 2.60, "weight": 2, "label": "T5YIE"},
            {"metric": "T5YIFR", "op": "between", "low": 2.00, "high": 2.40, "weight": 2, "label": "5y5y近似"},
            {"metric": "DGS2", "op": "between", "low": 3.50, "high": 3.85, "weight": 1, "label": "2年美债"},
            {"metric": "BAMLH0A0HYM2", "op": "<", "value": 4.50, "weight": 1, "label": "HY OAS"},
            {"metric": "SAHMREALTIME", "op": "<", "value": 0.30, "weight": 1, "label": "Sahm"},
            {"metric": "NFCI", "op": "<", "value": 0.20, "weight": 1, "label": "NFCI"},
        ],
        "anti_rules": [
            {"metric": "T5YIFR", "op": ">=", "value": 2.50, "weight": -2, "label": "5y5y近似"},
            {"metric": "SAHMREALTIME", "op": ">=", "value": 0.50, "weight": -3, "label": "Sahm"},
        ],
        "hard_triggers": [],
        "hard_bonus": 0,
    },
    {
        "key": "higher_for_longer",
        "label": "更高更久 / 通胀锚松动",
        "color": "yellow",
        "summary": "前端利率高位、通胀锚上修，市场不再相信顺畅宽松路径。",
        "rules": [
            {"metric": "DGS2", "op": ">=", "value": 3.85, "weight": 3, "label": "2年美债"},
            {"metric": "T5YIE", "op": ">=", "value": 2.70, "weight": 2, "label": "T5YIE"},
            {"metric": "T5YIFR", "op": ">=", "value": 2.50, "weight": 2, "label": "5y5y近似"},
            {"metric": "BRENT_OILPRICE", "op": ">=", "value": 105, "weight": 1, "label": "Brent"},
            {"metric": "VIXCLS", "op": "between", "low": 20, "high": 30, "weight": 1, "label": "VIX"},
            {"metric": "BAMLH0A0HYM2", "op": "between", "low": 3.5, "high": 5.0, "weight": 1, "label": "HY OAS"},
        ],
        "anti_rules": [
            {"metric": "DGS2", "op": "<", "value": 3.50, "weight": -3, "label": "2年美债"},
            {"metric": "T5YIFR", "op": "<", "value": 2.40, "weight": -2, "label": "5y5y近似"},
        ],
        "hard_triggers": [],
        "hard_bonus": 0,
    },
    {
        "key": "stagflation_test",
        "label": "滞胀压力测试",
        "color": "yellow",
        "summary": "油价高、近端通胀高、利率高，但信用与就业尚未完全进入事故区。",
        "rules": [
            {"metric": "BRENT_OILPRICE", "op": "between", "low": 105, "high": 120, "weight": 2, "label": "Brent"},
            {"metric": "T5YIE", "op": "between", "low": 2.55, "high": 2.90, "weight": 2, "label": "T5YIE"},
            {"metric": "DGS2", "op": "between", "low": 3.60, "high": 3.95, "weight": 2, "label": "2年美债"},
            {"metric": "BAMLH0A0HYM2", "op": "between", "low": 3.20, "high": 4.20, "weight": 1, "label": "HY OAS"},
            {"metric": "VIXCLS", "op": "between", "low": 20, "high": 30, "weight": 1, "label": "VIX"},
            {"metric": "NFCI", "op": "<", "value": 0.30, "weight": 1, "label": "NFCI"},
            {"metric": "ICSA_4W", "op": "between", "low": 230000, "high": 270000, "weight": 1, "label": "初请4周均值"},
            {"metric": "SAHMREALTIME", "op": "between", "low": 0.30, "high": 0.49, "weight": 2, "label": "Sahm"},
        ],
        "anti_rules": [
            {"metric": "BAMLH0A0HYM2", "op": ">=", "value": 5.00, "weight": -2, "label": "HY OAS"},
            {"metric": "SAHMREALTIME", "op": ">=", "value": 0.50, "weight": -3, "label": "Sahm"},
        ],
        "hard_triggers": [],
        "hard_bonus": 0,
    },
    {
        "key": "recession_confirmation",
        "label": "衰退确认",
        "color": "red",
        "summary": "就业、信用、波动率与金融条件共振恶化，开始进入衰退交易。",
        "rules": [
            {"metric": "SAHMREALTIME", "op": ">=", "value": 0.50, "weight": 3, "label": "Sahm"},
            {"metric": "ICSA_4W", "op": ">=", "value": 270000, "weight": 2, "label": "初请4周均值"},
            {"metric": "BAMLH0A0HYM2", "op": ">=", "value": 5.00, "weight": 2, "label": "HY OAS"},
            {"metric": "VIXCLS", "op": ">=", "value": 30, "weight": 1, "label": "VIX"},
            {"metric": "NFCI", "op": ">=", "value": 0.50, "weight": 2, "label": "NFCI"},
            {"metric": "DGS2", "op": "<", "value": 3.50, "weight": 1, "label": "2年美债"},
        ],
        "anti_rules": [
            {"metric": "SAHMREALTIME", "op": "<", "value": 0.40, "weight": -3, "label": "Sahm"},
            {"metric": "BAMLH0A0HYM2", "op": "<", "value": 4.00, "weight": -2, "label": "HY OAS"},
        ],
        "hard_triggers": [
            [
                {"metric": "SAHMREALTIME", "op": ">=", "value": 0.50},
                {"metric": "BAMLH0A0HYM2", "op": ">=", "value": 5.00},
            ]
        ],
        "hard_bonus": 2,
    },
    {
        "key": "credit_event",
        "label": "信用事故 / 流动性踩踏",
        "color": "red",
        "summary": "信用利差、波动率、金融条件同步恶化，市场进入应急定价阶段。",
        "rules": [
            {"metric": "BAMLH0A0HYM2", "op": ">=", "value": 6.00, "weight": 3, "label": "HY OAS"},
            {"metric": "VIXCLS", "op": ">=", "value": 35, "weight": 2, "label": "VIX"},
            {"metric": "NFCI", "op": ">=", "value": 1.00, "weight": 2, "label": "NFCI"},
            {"metric": "SAHMREALTIME", "op": ">=", "value": 0.50, "weight": 1, "label": "Sahm"},
            {"metric": "ICSA_4W", "op": ">=", "value": 300000, "weight": 1, "label": "初请4周均值"},
        ],
        "anti_rules": [
            {"metric": "BAMLH0A0HYM2", "op": "<", "value": 4.50, "weight": -3, "label": "HY OAS"},
            {"metric": "VIXCLS", "op": "<", "value": 25, "weight": -2, "label": "VIX"},
            {"metric": "NFCI", "op": "<", "value": 0, "weight": -2, "label": "NFCI"},
        ],
        "hard_triggers": [
            [
                {"metric": "BAMLH0A0HYM2", "op": ">=", "value": 6.00},
                {"metric": "VIXCLS", "op": ">=", "value": 35},
                {"metric": "NFCI", "op": ">=", "value": 1.00},
            ]
        ],
        "hard_bonus": 3,
    },
]


def run_scenario_engine(data_dict):
    metrics = build_current_metrics(data_dict)
    results = [score_scenario(metrics, s) for s in SCENARIOS]
    results = sorted(results, key=lambda x: x["ratio"], reverse=True)
    return metrics, results


def scenario_color_meta(color_key: str):
    meta = {
        "green": {"emoji": "🟢", "hex": "#16a34a"},
        "yellow": {"emoji": "🟡", "hex": "#f59e0b"},
        "red": {"emoji": "🔴", "hex": "#dc2626"},
    }
    return meta.get(color_key, meta["yellow"])


def render_scenario_header(results):
    top = results[0]
    runner = results[1] if len(results) > 1 else None
    confidence = compute_confidence(results)

    top_meta = scenario_color_meta(top["color"])
    st.subheader("🧭 当前宏观主情景")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("主情景", f"{top_meta['emoji']} {top['label']}")
    col2.metric("置信度", f"{confidence}%")
    col3.metric("情景得分", f"{int(top['ratio'] * 100)} / 100")
    col4.metric("次主情景", runner["label"] if runner else "N/A")

    st.caption(top["summary"])

    with st.container(border=True):
        st.markdown("**主情景判断依据**")
        if top["matched"]:
            for item in top["matched"][:4]:
                st.markdown(f"- {item}")
        else:
            st.markdown("- 当前命中项较少，更多是相对比较后的结果。")


def render_scenario_table(results):
    rows = []
    for r in results:
        meta = scenario_color_meta(r["color"])
        rows.append({
            "状态": f"{meta['emoji']} {r['label']}",
            "得分": round(r["score"], 2),
            "标准化得分": f"{int(r['ratio'] * 100)}",
            "命中项": len(r["matched"]),
            "脱靶项": len(r["missing"]),
            "冲突项": len(r["conflicts"]),
            "硬触发": "是" if r["hard_trigger_hit"] else "否",
            "说明": r["summary"],
        })

    df = pd.DataFrame(rows)
    st.subheader("📋 情景打分表")
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_scenario_details(results):
    st.subheader("🔍 情景命中 / 脱靶详情")

    for r in results:
        meta = scenario_color_meta(r["color"])
        with st.expander(f"{meta['emoji']} {r['label']}｜标准化得分 {int(r['ratio'] * 100)}"):
            left, right = st.columns(2)

            with left:
                st.markdown("**已命中条件**")
                if r["matched"]:
                    for item in r["matched"]:
                        st.markdown(f"- {item}")
                else:
                    st.markdown("- 无")

            with right:
                st.markdown("**未满足 / 冲突条件**")
                if r["missing"]:
                    for item in r["missing"][:5]:
                        st.markdown(f"- 脱靶：{item}")
                if r["conflicts"]:
                    for item in r["conflicts"]:
                        st.markdown(f"- 冲突：{item}")
                if not r["missing"] and not r["conflicts"]:
                    st.markdown("- 无")


def render_transition_watchlist(results):
    st.subheader("🎯 下一步最值得盯的切换条件")

    if len(results) < 2:
        st.info("情景数量不足，无法生成切换观察点。")
        return

    top = results[0]
    runner = results[1]

    st.markdown(f"当前主情景：**{top['label']}**")
    st.markdown(f"最接近的次主情景：**{runner['label']}**")

    st.markdown("**若以下条件逐步满足，情景更可能向次主情景切换：**")
    if runner["missing"]:
        for item in runner["missing"][:4]:
            st.markdown(f"- {item}")
    else:
        st.markdown("- 次主情景的核心条件已经大多满足，说明市场正处在切换边缘。")

    st.markdown("**若以下冲突项缓和，当前主情景会更稳；若恶化，则可能降级/升级：**")
    if top["conflicts"]:
        for item in top["conflicts"][:4]:
            st.markdown(f"- {item}")
    else:
        st.markdown("- 当前主情景内部冲突项较少。")

def get_group_latest_date(data_dict, monitors) -> Optional[pd.Timestamp]:
    """
    取一组监控项里最新的可用日期，作为该警示卡最近更新时间
    monitors: [(label, code, value, rule), ...]
    """
    dates = []
    for _, code, _, _ in monitors:
        dt = get_latest_date(data_dict, code)
        if dt is not None:
            dates.append(pd.to_datetime(dt))
    if not dates:
        return None
    return max(dates)



def format_alert_value(code: str, value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    if code in {"WTI_OILPRICE", "BRENT_OILPRICE"}:
        return f"${value:.2f}"
    if code == "ICSA":
        return f"{int(value):,}"
    return f"{value:.2f}"


def build_alert_groups(data_dict):
    """
    构建多组警示规则
    返回 [{'title', 'status', 'headline', 'detail', 'monitors'}]
    status: green / yellow / red
    """
    brent = get_latest_value(data_dict, "BRENT_OILPRICE")
    wti = get_latest_value(data_dict, "WTI_OILPRICE")
    t5yie = get_latest_value(data_dict, "T5YIE")
    t5yifr = get_latest_value(data_dict, "T5YIFR")
    dgs2 = get_latest_value(data_dict, "DGS2")
    hy_oas = get_latest_value(data_dict, "BAMLH0A0HYM2")
    vix = get_latest_value(data_dict, "VIXCLS")
    nfci = get_latest_value(data_dict, "NFCI")
    icsa_4w = get_rolling_mean(data_dict, "ICSA", 4)
    sahm = get_latest_value(data_dict, "SAHMREALTIME")

    alerts = []

    # ======================
    # 第一组：油价冲击是否正在持续化并向通胀传导
    # ======================
    oil_red = (
        brent is not None and t5yie is not None and
        brent >= 105 and t5yie >= 2.7 
    )
    oil_yellow_signals = [
        brent is not None and brent >= 95,
        t5yie is not None and t5yie >= 2.5,
        t5yifr is not None and t5yifr >= 2.4,
    ]
    oil_yellow = sum(oil_yellow_signals) >= 2 and not oil_red

    if oil_red:
        if t5yifr is not None and t5yifr >= 2.5:
            oil_headline = "红色：油价冲击已明显传导，且长期通胀锚有松动迹象"
            oil_detail = "Brent、T5YIE、CPI 同时达到高风险区，且 5y5y 进一步走高，更接近“近端冲击+长期预期松动”组合。"
        else:
            oil_headline = "红色：油价冲击正在向通胀传导"
            oil_detail = "Brent、T5YIE、CPI 同时进入高风险区，但 5y5y 若仍相对稳定，更像近端通胀冲击而非长期失锚。"
        oil_status = "red"
    elif oil_yellow:
        oil_headline = "黄色：油价与通胀预期开始共振，需重点跟踪"
        oil_detail = "已出现至少两项预警信号，说明冲击可能正在从能源价格向通胀预期传导，但尚未形成强确认。"
        oil_status = "yellow"
    else:
        oil_headline = "绿色：当前更像事件性扰动，未见显著持续化传导"
        oil_detail = "油价、近端通胀预期与 CPI 未同时进入高风险区，暂不支持“新一轮通胀 regime”判断。"
        oil_status = "green"

    alerts.append({
        "title": "① 油价冲击 → 通胀传导",
        "status": oil_status,
        "headline": oil_headline,
        "detail": oil_detail,
        "monitors": [
            ("Brent", "BRENT_OILPRICE", brent, "红线 ≥ 105；关注线 ≥ 95"),
            ("WTI", "WTI_OILPRICE", wti, "辅助观察"),
            ("T5YIE", "T5YIE", t5yie, "红线 ≥ 2.7；关注线 ≥ 2.5"),
            ("5y5y近似(T5YIFR)", "T5YIFR", t5yifr, "锚定区 2.2~2.4；>2.5 偏危险"),
        ]
    })

    # ======================
    # 第二组：政策是否“暂停更久 / 更高更久”
    # ======================
    policy_red = (
        dgs2 is not None and dgs2 >= 3.85 and
        (
            (brent is not None and brent >= 105) or
            (t5yie is not None and t5yie >= 2.7)
        )
    )

    policy_yellow = (
        dgs2 is not None and (
            3.50 <= dgs2 < 3.85 or
            (dgs2 >= 3.60 and brent is not None and brent >= 100)
        )
    ) and not policy_red

    if policy_red:
        policy_status = "red"
        policy_headline = "红色：市场在定价“更久不降”甚至更鹰尾部"
        policy_detail = "2年美债已逼近/突破 3.85%，且油价或通胀预期未回落，说明政策宽松路径被明显打断。"
    elif policy_yellow:
        policy_status = "yellow"
        policy_headline = "黄色：政策处于暂停观察期"
        policy_detail = "2年美债仍在高位，市场尚未重新相信联储会恢复顺畅宽松。"
    else:
        policy_status = "green"
        policy_headline = "绿色：政策约束有所缓和"
        policy_detail = "2年美债回落到相对温和区间，市场对宽松路径的信心有所修复。"

    alerts.append({
        "title": "② 政策暂停 / 更高更久",
        "status": policy_status,
        "headline": policy_headline,
        "detail": policy_detail,
        "monitors": [
            ("2年美债", "DGS2", dgs2, "红线 ≥ 3.85；宽松修复参考 < 3.50"),
            ("Brent", "BRENT_OILPRICE", brent, "高油价会抬高政策约束"),
            ("T5YIE", "T5YIE", t5yie, "高通胀预期会抬高政策约束"),
        ]
    })

    # ======================
    # 第三组：风险是否扩散到信用与增长
    # ======================
    spread_red_signals = [
        hy_oas is not None and hy_oas >= 4.25,
        vix is not None and vix >= 30,
        nfci is not None and nfci >= 0,
        icsa_4w is not None and icsa_4w >= 270000,
        sahm is not None and sahm >= 0.50,
    ]
    spread_yellow_signals = [
        hy_oas is not None and hy_oas >= 3.75,
        vix is not None and vix >= 28,
        nfci is not None and nfci >= 0,
        icsa_4w is not None and icsa_4w >= 230000,
        sahm is not None and sahm >= 0.40,
    ]

    spread_red = sum(spread_red_signals) >= 2
    spread_yellow = sum(spread_yellow_signals) >= 2 and not spread_red

    if spread_red:
        spread_status = "red"
        spread_headline = "红色：压力已向信用与增长层面扩散"
        spread_detail = "这不再只是油价或估值扰动，而是融资条件、波动率、就业前导与衰退信号正在共振恶化。"
    elif spread_yellow:
        spread_status = "yellow"
        spread_headline = "黄色：信用与增长开始出现传导压力"
        spread_detail = "已出现多项黄灯信号，说明市场压力正在从资产价格向实体与融资条件扩散。"
    else:
        spread_status = "green"
        spread_headline = "绿色：当前仍以估值/风险偏好重定价为主"
        spread_detail = "信用、金融条件与就业前导尚未同步恶化，暂不支持“信用事故”判断。"

    alerts.append({
        "title": "③ 信用 / 增长扩散",
        "status": spread_status,
        "headline": spread_headline,
        "detail": spread_detail,
        "monitors": [
            ("HY OAS", "BAMLH0A0HYM2", hy_oas, "黄线 ≥ 3.75；红线 ≥ 4.25"),
            ("VIX", "VIXCLS", vix, "黄线 ≥ 28；红线 ≥ 30"),
            ("NFCI", "NFCI", nfci, "黄/红线 ≥ 0"),
            ("初请4周均值", "ICSA", icsa_4w, "黄线 ≥ 230k；红线 ≥ 270k"),
            ("Sahm Rule", "SAHMREALTIME", sahm, "黄线 ≥ 0.40；红线 ≥ 0.50"),
        ]
    })

    return alerts


def render_alert_board(alerts, data_dict):
    st.subheader("🚨 宏观警示看板")
    st.caption("按多组指标组合阈值进行绿 / 黄 / 红预警；颜色越深，说明越接近从“估值重定价”向“通胀/信用/增长压力扩散”切换。")

    status_meta = {
        "green": {"label": "绿色", "color": "#16a34a"},
        "yellow": {"label": "黄色", "color": "#f59e0b"},
        "red": {"label": "红色", "color": "#dc2626"},
    }

    cols = st.columns(len(alerts))
    for col, alert in zip(cols, alerts):
        with col:
            meta = status_meta.get(alert["status"], status_meta["green"])
            latest_dt = get_group_latest_date(data_dict, alert["monitors"])
            latest_dt_text = latest_dt.strftime("%Y-%m-%d") if latest_dt is not None else "N/A"

            with st.container(border=True):
                # 标题 + 小圆点状态
                st.markdown(
                    f"""
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.35rem;">
                        <div style="font-weight:700;">{alert['title']}</div>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="
                                display:inline-block;
                                width:10px;
                                height:10px;
                                border-radius:50%;
                                background:{meta['color']};
                            "></span>
                            <span style="font-size:0.9rem; color:{meta['color']}; font-weight:600;">
                                {meta['label']}
                            </span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # 顶部状态色条
                st.markdown(
                    f"""
                    <div style="
                        width:100%;
                        height:8px;
                        border-radius:999px;
                        background:{meta['color']};
                        opacity:0.9;
                        margin-bottom:0.75rem;
                    "></div>
                    """,
                    unsafe_allow_html=True,
                )

                # 最近更新时间
                st.caption(f"最近更新时间：{latest_dt_text}")

                if alert["status"] == "green":
                    st.success(alert["headline"])
                elif alert["status"] == "yellow":
                    st.warning(alert["headline"])
                else:
                    st.error(alert["headline"])

                st.caption(alert["detail"])

                st.markdown("**当前监控值**")
                for label, code, val, rule in alert["monitors"]:
                    metric_dt = get_latest_date(data_dict, code)
                    metric_dt_text = metric_dt.strftime("%Y-%m-%d") if metric_dt is not None else "N/A"
                    st.markdown(
                        f"- **{label}**：{format_alert_value(code, val)}  \n"
                        f"  <span style='color:gray'>{rule}｜更新时间：{metric_dt_text}</span>",
                        unsafe_allow_html=True
                    )

# ====================== 主页面 ======================
st.title("📊 宏观指标交互式监控仪表盘")
st.divider()

with st.spinner("正在拉取最新数据..."):
    data_dict = get_macro_data()
    
# ----------------------
# 侧边栏：交互配置
# ----------------------
with st.sidebar:
    st.header("⚙️ 交互配置")

    st.subheader("1. 时间范围")
    all_dates = []
    for df in data_dict.values():
        if not df.empty:
            all_dates.extend(df.index.tolist())

    min_date = pd.to_datetime(min(all_dates)) if all_dates else pd.to_datetime("2018-01-01")
    max_date = pd.to_datetime(max(all_dates)) if all_dates else pd.to_datetime(date.today())

    start_date = st.date_input(
        "起始日期",
        value=min_date,
        min_value=min_date,
        max_value=max_date
    )
    end_date = st.date_input(
        "结束日期",
        value=max_date,
        min_value=min_date,
        max_value=max_date
    )

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    st.subheader("2. 指标选择")
    single_code = st.selectbox(
        "单独查看指标",
        options=list(INDICATORS.keys()),
        format_func=lambda x: INDICATORS[x]["name"],
        index=0
    )

    selected_codes = st.multiselect(
        "叠加对比指标",
        options=list(INDICATORS.keys()),
        format_func=lambda x: INDICATORS[x]["name"],
        default=[single_code],
    )

# ----------------------
# 主体内容
# ----------------------
tab1, tab2, tab3, tab4 = st.tabs(
    ["📈 单个指标详情", "🔄 多指标叠加对比", "🚨 宏观警示看板", "🧭 情景分析"]
)

with tab1:
    st.subheader(f"{INDICATORS[single_code]['name']} - 详情")
    st.caption(INDICATORS[single_code]["desc"])

    df_single = data_dict[single_code]
    if not df_single.empty:
        df_filtered = df_single[
            (df_single.index >= start_dt) &
            (df_single.index <= end_dt)
        ]

        if not df_filtered.empty:
            is_oil = INDICATORS[single_code]["source"] == "oilprice"

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_filtered.index,
                y=df_filtered[INDICATORS[single_code]["name"]],
                mode="lines+markers",
                line=dict(color=INDICATORS[single_code]["color"], width=2),
                hovertemplate=(
                    "📅 日期: %{x}<br>"
                    + ("💵 价格: $%{y:.2f}<br>" if is_oil else "📊 数值: %{y:.2f}<br>")
                    + "<extra></extra>"
                ),
                name=INDICATORS[single_code]["name"]
            ))

            actual_start = df_filtered.index.min().strftime("%Y-%m-%d")
            actual_end = df_filtered.index.max().strftime("%Y-%m-%d")

            fig.update_layout(
                title=f"{INDICATORS[single_code]['name']}（实际数据区间：{actual_start} 至 {actual_end}）",
                xaxis_title="日期",
                yaxis_title="价格 (USD)" if is_oil else "数值",
                hovermode="x unified",
                height=600,
                template="plotly_white"
            )

            st.plotly_chart(fig, use_container_width=True)

            # 最新数据展示
            st.subheader("📌 最新数据")
            latest_row = df_filtered.iloc[-1]
            col1, col2, col3 = st.columns(3)

            if single_code == "ICSA":
                latest_text = f"{int(latest_row.iloc[0]):,}"
            elif is_oil:
                latest_text = f"${latest_row.iloc[0]:.2f}"
            else:
                latest_text = f"{latest_row.iloc[0]:.2f}"

            col1.metric("最新值", latest_text)
            col2.metric("最新日期", latest_row.name.strftime("%Y-%m-%d"))
            col3.metric("数据条数", len(df_filtered))
        else:
            st.warning(f"该时间范围（{start_date} 至 {end_date}）内无数据")
    else:
        st.warning("暂无有效数据")

with tab2:
    st.subheader("多指标叠加对比")
    st.caption("支持多指标叠加，每个指标使用独立纵轴，鼠标悬停可查看各自数值")

    merged_df = merge_selected_data(selected_codes, data_dict)
    if not merged_df.empty:
        df_merged_filtered = merged_df[
            (merged_df.index >= start_dt) &
            (merged_df.index <= end_dt)
        ]

        if not df_merged_filtered.empty:
            fig = go.Figure()

            valid_codes = [
                code for code in selected_codes
                if code in INDICATORS and INDICATORS[code]["name"] in df_merged_filtered.columns
            ]

            if not valid_codes:
                st.warning("当前所选指标在该时间范围内无有效数据")
            else:
                if len(valid_codes) > 6:
                    st.info("当前指标较多，独立纵轴会比较拥挤，建议控制在 4-6 个以内。")

                left_axes = []
                right_axes = []

                for i, code in enumerate(valid_codes):
                    cfg = INDICATORS[code]
                    col_name = cfg["name"]
                    is_oil = cfg["source"] == "oilprice"

                    axis_ref = "y" if i == 0 else f"y{i+1}"
                    axis_layout_key = "yaxis" if i == 0 else f"yaxis{i+1}"
                    side = "left" if i % 2 == 0 else "right"

                    if side == "left":
                        left_index = len(left_axes)
                        position = max(0.02, 0.10 - left_index * 0.04)
                        left_axes.append(axis_ref)
                    else:
                        right_index = len(right_axes)
                        position = min(0.98, 0.90 + right_index * 0.04)
                        right_axes.append(axis_ref)

                    if code == "ICSA":
                        hover_tmpl = (
                            f"📅 日期: %{{x}}<br>"
                            f"📊 {cfg['name']}: %{{y:,.0f}}<br>"
                            "<extra></extra>"
                        )
                        axis_title = cfg["name"]
                    elif is_oil:
                        hover_tmpl = (
                            f"📅 日期: %{{x}}<br>"
                            f"💵 {cfg['name']}: $%{{y:.2f}}<br>"
                            "<extra></extra>"
                        )
                        axis_title = f"{cfg['name']}（美元）"
                    else:
                        hover_tmpl = (
                            f"📅 日期: %{{x}}<br>"
                            f"📊 {cfg['name']}: %{{y:.2f}}<br>"
                            "<extra></extra>"
                        )
                        axis_title = cfg["name"]

                    fig.add_trace(go.Scatter(
                        x=df_merged_filtered.index,
                        y=df_merged_filtered[col_name],
                        mode="lines",
                        line=dict(color=cfg["color"], width=2),
                        hovertemplate=hover_tmpl,
                        name=cfg["name"],
                        yaxis=axis_ref
                    ))

                    axis_config = dict(
                        title=dict(text=axis_title, font=dict(color=cfg["color"])),
                        tickfont=dict(color=cfg["color"]),
                        showgrid=(i == 0),
                        zeroline=False,
                        side=side,
                    )

                    if i != 0:
                        axis_config.update(
                            overlaying="y",
                            anchor="free",
                            position=position,
                        )

                    fig.update_layout(**{axis_layout_key: axis_config})

                actual_start = df_merged_filtered.index.min().strftime("%Y-%m-%d")
                actual_end = df_merged_filtered.index.max().strftime("%Y-%m-%d")

                fig.update_layout(
                    title=f"多指标独立纵轴对比 ({actual_start} 至 {actual_end})",
                    xaxis=dict(
                        title="日期",
                        domain=[0.12, 0.88],
                    ),
                    hovermode="x unified",
                    height=700,
                    template="plotly_white",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.25,
                        xanchor="center",
                        x=0.5,
                    ),
                    margin=dict(l=90, r=90, t=80, b=120),
                )

                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"该时间范围（{start_date} 至 {end_date}）内无数据")
    else:
        st.warning("请选择至少1个有效指标")

with tab3:
    alerts = build_alert_groups(data_dict)
    render_alert_board(alerts, data_dict)

with tab4:
    st.subheader("情景分析")
    st.caption("基于油价、通胀预期、前端利率、信用利差、波动率、金融条件与就业前导指标，对当前宏观环境进行综合判定。")

    metrics, scenario_results = run_scenario_engine(data_dict)

    render_scenario_header(scenario_results)
    st.divider()

    # 当前关键指标快照
    st.subheader("📌 当前关键指标快照")
    snap_cols = st.columns(5)
    snapshot_items = [
        ("Brent", "BRENT_OILPRICE"),
        ("T5YIE", "T5YIE"),
        ("5y5y近似", "T5YIFR"),
        ("2年美债", "DGS2"),
        ("HY OAS", "BAMLH0A0HYM2"),
        ("VIX", "VIXCLS"),
        ("NFCI", "NFCI"),
        ("初请4周均值", "ICSA_4W"),
        ("Sahm", "SAHMREALTIME"),
    ]

    for i, (label, code) in enumerate(snapshot_items):
        with snap_cols[i % 5]:
            value = metrics.get(code)
            st.metric(label, format_metric_value(code, value))

    st.divider()
    render_scenario_table(scenario_results)
    with st.expander("📘 评分规则说明", expanded=False):
        rule_df = pd.DataFrame([
            {
                "指标": "情景得分",
                "公式 / 规则": "正向命中得分 - 冲突项扣分 + 硬触发加分",
                "含义": "反映某个情景当前“像不像”"
            },
            {
                "指标": "最大得分",
                "公式 / 规则": "所有正向规则权重之和 + hard_bonus",
                "含义": "作为该情景的理论满分，用于后续归一化"
            },
            {
                "指标": "标准化得分",
                "公式 / 规则": "max(0, min(1, score / max_score))",
                "含义": "把不同情景压到同一尺度，便于横向比较"
            },
            {
                "指标": "置信度",
                "公式 / 规则": "top_ratio * 75 + gap * 80，再限制在 35%~95%",
                "含义": "衡量当前主情景判断的稳固程度"
            },
        ])
        st.dataframe(rule_df, use_container_width=True, hide_index=True)

        st.markdown("**补充说明**")
        st.markdown(
            """
- **正向命中得分**：某情景的 `rules` 被满足时，加上对应权重。  
- **冲突项扣分**：某情景的 `anti_rules` 被满足时，扣掉对应权重。  
- **硬触发加分**：当某组 `hard_triggers` 同时成立时，额外加上 `hard_bonus`。  
- **top_ratio**：主情景的标准化得分。  
- **gap**：主情景与次主情景的标准化得分差值。  
            """
        )
    st.divider()
    render_transition_watchlist(scenario_results)
    st.divider()
    render_scenario_details(scenario_results)
    
# 底部说明
st.divider()
st.caption(
    "💡 核心交互说明：\n"
    "1. 鼠标悬停在曲线上可显示「日期+精确数值」；\n"
    "2. 侧边栏可自定义时间范围；\n"
    "3. 支持单个指标详情 / 多指标叠加对比；\n"
    "4. 图表可缩放、下载、平移。\n\n"
)
