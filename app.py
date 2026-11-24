import pandas as pd
import re
import streamlit as st

st.set_page_config(page_title="标注工作量看板", layout="wide")
st.title("📊 数据标注工作量看板")

TARGET_COLS = {
    'username':      ['用户名', '姓名', '标注员'],
    'stage':         ['阶段'],
    'project_name':  ['项目名称', '项目名'],
    'work_hours':    ['总时长（小时数）', '总时长(小时数)', '总时长', '工作时长'],
    'workload':      ['初次工作量'],
    'image_count':   ['初次图片数'],
    'acc_image':     ['图片准确率'],
    'acc_object':    ['对象准确率'],
    'acc_standard':  ['标准准确率'],
    'acc_combined':  ['综合标记准确率'],
    'acc_storage':   ['入库标记准确率'],
}

def normalize(s):
    if not isinstance(s, str):
        return ''
    s = s.strip().replace('（', '(').replace('）', ')')
    return re.sub(r'\s+', '', s)

def resolve_columns(df_columns):
    norm_map = {normalize(c): c for c in df_columns}
    resolved, missing = {}, []
    for field, aliases in TARGET_COLS.items():
        hit = None
        for a in aliases:
            if a in df_columns:
                hit = a; break
        if hit is None:
            for a in aliases:
                if normalize(a) in norm_map:
                    hit = norm_map[normalize(a)]; break
        if hit is None:
            for a in aliases:
                na = normalize(a)
                for nc, orig in norm_map.items():
                    if na and na in nc:
                        hit = orig; break
                if hit: break
        if hit is None:
            missing.append(field)
        resolved[field] = hit
    return resolved, missing

def extract_last_pct(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s in ('-', '', 'nan'):
        return None
    if '|' in s:
        s = s.split('|')[-1]
    try:
        return float(s)
    except ValueError:
        return None

def parse_excel(path):
    df = pd.read_excel(path, sheet_name=0)
    dups = pd.Series([normalize(c) for c in df.columns]).duplicated(keep=False)
    if dups.any():
        dup_names = [c for c, d in zip(df.columns, dups) if d]
        raise ValueError(f"检测到重复/易混淆列名：{dup_names}，请人工确认")
    resolved, missing = resolve_columns(df.columns)
    if missing:
        raise ValueError(f"以下字段未找到对应列：{missing}\n实际列名：{list(df.columns)}")
    
    df = df[[resolved[f] for f in TARGET_COLS]].rename(
        columns={resolved[f]: f for f in TARGET_COLS})
        
    for c in ['work_hours','workload','image_count']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    for c in ['acc_image','acc_object','acc_standard']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
        
    df['acc_combined'] = df['acc_combined'].map(extract_last_pct)
    df['acc_storage']  = df['acc_storage'].map(extract_last_pct)
    
    # 把 0 视作没有数据，显示为 None
    acc_cols = ['acc_image','acc_object','acc_standard','acc_combined','acc_storage']
    for c in acc_cols:
        df[c] = df[c].apply(lambda x: None if x == 0 else x)

    return df, resolved

# ---------- 页面 ----------
uploaded = st.file_uploader("上传平台导出的 Excel", type=["xlsx"])
if uploaded:
    try:
        df, resolved = parse_excel(uploaded)
    except Exception as e:
        st.error(str(e))
        st.stop()

    with st.expander("🔍 列映射结果（确认字段有没有对错）"):
        for f, a in resolved.items():
            st.write(f"{f:15s}  ←  {a}")

    # ----- 筛选区域（优化版） -----
    # 第一排：姓名搜索 + 项目搜索
    c_name, c_proj = st.columns(2)
    name_kw = c_name.text_input("🔍 姓名搜索")
    proj_kw = c_proj.text_input("🔍 项目搜索（支持模糊匹配）")

    # 第二排：阶段筛选
    stage_opt = st.multiselect("阶段筛选", df['stage'].dropna().unique())

    # 执行筛选逻辑
    view = df.copy()
    if stage_opt:
        view = view[view['stage'].isin(stage_opt)]
    if name_kw:
        view = view[view['username'].astype(str).str.contains(name_kw, case=False, na=False)]
    if proj_kw:
        view = view[view['project_name'].astype(str).str.contains(proj_kw, case=False, na=False)]

    # 顶部汇总卡片
    c1, c2, c3 = st.columns(3)
    c1.metric("记录行数", len(view))
    c2.metric("总工作量", f"{int(view['workload'].sum()):,}")
    c3.metric("总图片数", f"{int(view['image_count'].sum()):,}")

    # 表格展示
    show = view.rename(columns={
        'username':'姓名','stage':'阶段','project_name':'项目',
        'work_hours':'时长(h)','workload':'初次工作量','image_count':'初次图片数',
        'acc_image':'图片准确率','acc_object':'对象准确率','acc_standard':'标准准确率',
        'acc_combined':'综合标记准确率','acc_storage':'入库标记准确率'})
    cols = ['姓名','阶段','项目','时长(h)','初次工作量','初次图片数',
            '图片准确率','对象准确率','标准准确率','综合标记准确率','入库标记准确率']
    show = show[cols]
    acc_cols = cols[6:]

    def color_acc(v):
        if pd.isna(v): return ''
        if v >= 95: return 'background-color:#d4edda'
        if v >= 90: return 'background-color:#fff3cd'
        return 'background-color:#f8d7da'

    st.subheader("📋 明细表（一人可多行）")
    
    # 格式化字典：工作量不显示小数，准确率保留2位
    fmt_dict = {
        '时长(h)': '{:.2f}', 
        '初次工作量': '{:,.0f}', 
        '初次图片数': '{:,.0f}'
    }
    for c in acc_cols:
        fmt_dict[c] = '{:.2f}'

    st.dataframe(
        show.style.map(color_acc, subset=acc_cols).format(fmt_dict, na_rep='-'),
        use_container_width=True, height=600)