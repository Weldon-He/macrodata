# -*- coding: utf-8 -*-
"""
Created on Tue Mar 24 17:30:52 2026

@author: AAA20
"""

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
    "CPIAUCSL": {"name": "美国CPI同比", "desc": "消费者物价指数，衡量通胀水平", "color": "#bcbd22", "source": "fred"},
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
tab1, tab2 = st.tabs(["📈 单个指标详情", "🔄 多指标叠加对比"])

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
    st.caption("支持多指标叠加，鼠标悬停可查看每个指标的数值")

    merged_df = merge_selected_data(selected_codes, data_dict)
    if not merged_df.empty:
        df_merged_filtered = merged_df[
            (merged_df.index >= start_dt) &
            (merged_df.index <= end_dt)
        ]

        if not df_merged_filtered.empty:
            fig = go.Figure()

            for code in selected_codes:
                cfg = INDICATORS[code]
                if cfg["name"] in df_merged_filtered.columns:
                    is_oil = cfg["source"] == "oilprice"

                    # 自定义hover模板
                    if code == "ICSA":
                        hover_tmpl = (
                            f"📅 日期: %{{x}}<br>"
                            f"📊 {cfg['name']}: %{{y:,.0f}}<br>"
                            "<extra></extra>"
                        )
                    elif is_oil:
                        hover_tmpl = (
                            f"📅 日期: %{{x}}<br>"
                            f"💵 {cfg['name']}: $%{{y:.2f}}<br>"
                            "<extra></extra>"
                        )
                    else:
                        hover_tmpl = (
                            f"📅 日期: %{{x}}<br>"
                            f"📊 {cfg['name']}: %{{y:.2f}}<br>"
                            "<extra></extra>"
                        )

                    fig.add_trace(go.Scatter(
                        x=df_merged_filtered.index,
                        y=df_merged_filtered[cfg["name"]],
                        mode="lines",
                        line=dict(color=cfg["color"], width=2),
                        hovertemplate=hover_tmpl,
                        name=cfg["name"]
                    ))
            
            actual_start = df_merged_filtered.index.min().strftime("%Y-%m-%d")
            actual_end = df_merged_filtered.index.max().strftime("%Y-%m-%d")
            
            fig.update_layout(
                title=f"多指标叠加对比 ({actual_start} 至 {actual_end})",
                xaxis_title="日期",
                yaxis_title="数值 / 价格 (USD)",
                hovermode="x unified",
                height=600,
                template="plotly_white",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.2,
                    xanchor="center",
                    x=0.5
                )
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"该时间范围（{start_date} 至 {end_date}）内无数据")
    else:
        st.warning("请选择至少1个有效指标")

# 底部说明
st.divider()
st.caption(
    "💡 核心交互说明：\n"
    "1. 鼠标悬停在曲线上可显示「日期+精确数值」；\n"
    "2. 侧边栏可自定义时间范围；\n"
    "3. 支持单个指标详情 / 多指标叠加对比；\n"
    "4. 图表可缩放、下载、平移。\n\n"
    "🔧 部署说明：需在 Streamlit Secrets 中配置 FRED_API_KEY（必填）和 OILPRICE_API_KEY（可选）"
)