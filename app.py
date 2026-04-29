import streamlit as st
import pandas as pd
from supabase import create_client
import numpy as np
from datetime import datetime, timedelta
import unicodedata
import re
from io import BytesIO

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Ave-Maria | Análise de Fretes", layout="wide")

# CSS Original (CSL Style)
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .metric-card {
        background-color: #ffffff;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e2e8f0;
        text-align: center;
        margin-bottom: 20px;
    }
    .metric-label {
        font-size: 12px;
        color: #64748b;
        margin-bottom: 8px;
        font-weight: 700;
        text-transform: uppercase;
    }
    .metric-value {
        font-size: 24px;
        color: #1e293b;
        font-weight: 800;
    }
    .hist-header {
        background: #f1f5f9;
        padding: 10px 15px;
        border-radius: 8px;
        border-left: 5px solid #3b82f6;
        margin-bottom: 5px;
    }
    h1, h2, h3 { color: #0f172a !important; font-weight: 800 !important; }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])                

supabase = init_connection()

def format_brl(val):
    if pd.isna(val) or val == 0: return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_kg(val):
    if pd.isna(val) or val == 0: return "0,00 kg"
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " kg"

def super_limpeza(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).strip().upper()
    txt = re.sub(r'\s+', ' ', txt) 
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

# MOTOR DE CÁLCULO CORRIGIDO
def engine_calculo(df_base, selecionadas, df_ts):
    df_final = df_base.copy()
    n_linhas = len(df_base)
    
    col_cid_nome = next((c for c in df_base.columns if 'CIDADE' in c.upper()), df_base.columns[2] if len(df_base.columns) > 2 else "CIDADE")
    col_uf_nome = next((c for c in df_base.columns if c.upper() == 'UF'), df_base.columns[3] if len(df_base.columns) > 3 else "UF")
    col_peso_nome = next((c for c in df_base.columns if 'PESO' in c.upper() and 'BASE' not in c.upper()), df_base.columns[6] if len(df_base.columns) > 6 else "PESO")
    col_valor_nome = next((c for c in df_base.columns if 'VALOR' in c.upper() and 'FRETE' not in c.upper()), df_base.columns[7] if len(df_base.columns) > 7 else "VALOR")
    
    cid_notas = df_base[col_cid_nome].astype(str).apply(super_limpeza).values
    uf_notas = df_base[col_uf_nome].astype(str).apply(super_limpeza).values
    pesos_notas = pd.to_numeric(df_base[col_peso_nome], errors='coerce').fillna(0).values
    valores_notas = pd.to_numeric(df_base[col_valor_nome], errors='coerce').fillna(0).values

    for t_nome in selecionadas:
        t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
        m, df_tab, df_abr = t_r['mapeamento_json'], pd.DataFrame(t_r['tabela_json']), pd.DataFrame(t_r['cidades_json'])
        
        df_abr['cid_clean'] = df_abr[m['ap_cidade']].astype(str).apply(super_limpeza)
        df_abr['uf_clean'] = df_abr[m.get('ap_uf', m['ap_cidade'])].astype(str).apply(super_limpeza)
        
        dic_ponte = {(row['cid_clean'], row['uf_clean']): super_limpeza(row[m['ap_sigla']]) for _, row in df_abr.iterrows()}
        siglas_match = [dic_ponte.get((c, u), "ND") for c, u in zip(cid_notas, uf_notas)]

        df_tab['sig_clean'] = df_tab[m['tab_sigla']].astype(str).apply(super_limpeza)
        df_tab_idx = df_tab.drop_duplicates(subset=['sig_clean']).set_index('sig_clean')
        
        def get_v(col_name): 
            if col_name and col_name != "Não mapear" and col_name in df_tab_idx.columns:
                return np.array([df_tab_idx.at[sig, col_name] if sig in df_tab_idx.index else 0 for sig in siglas_match], dtype=float)
            return np.zeros(n_linhas)
        
        f_peso = np.zeros(n_linhas); v_kg_adic = np.zeros(n_linhas)
        mask_atendida = np.array([s != "ND" for s in siglas_match])
        
        for faixa in m['faixas']:
            v_f = get_v(faixa['col'])
            mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0) & mask_atendida
            f_peso[mask] = v_f[mask]
            
        u_max = m['faixas'][-1]['max'] if m['faixas'] else 0
        mask_e = (pesos_notas > u_max) & mask_atendida
        if mask_e.any():
            v_b = get_v(m['faixas'][-1]['col']); v_ex = get_v(m['kg_extra'])
            v_kg_adic[mask_e] = (pesos_notas[mask_e] - u_max) * v_ex[mask_e]
            f_peso[mask_e] = v_b[mask_e] + v_kg_adic[mask_e]
        
        adv = np.maximum(valores_notas * get_v(m['taxas'].get("Ad Valorem %")), get_v(m['taxas'].get("Ad Valorem Min")))
        grs = np.maximum(valores_notas * get_v(m['taxas'].get("Gris %")), get_v(m['taxas'].get("Gris Min")))
        emx = np.maximum(valores_notas * get_v(m['taxas'].get("Emex %")), get_v(m['taxas'].get("Emex Min")))
        ped = np.ceil(pesos_notas/100) * get_v(m['taxas'].get("Pedagio"))
        
        frete_parcial = (f_peso + adv + grs + emx + ped + get_v(m['taxas'].get("TAS")) + get_v(m['taxas'].get("CTRC")) + 
                         get_v(m['taxas'].get("Suframa")) + get_v(m['taxas'].get("SEC-CAT")) + (valores_notas * get_v(m['taxas'].get("Fluvial"))) + 
                         (valores_notas * get_v(m['taxas'].get("Redespacho Fluvial"))) + np.maximum(valores_notas * get_v(m['taxas'].get("TDA %")), get_v(m['taxas'].get("TDA Min"))) + 
                         get_v(m['taxas'].get("Despacho")))
        
        trt = frete_parcial * get_v(m['taxas'].get("TRT %"))
        frete_total = (frete_parcial + trt) * mask_atendida

        df_final[f'PESO_BASE_{t_nome}'] = (f_peso - v_kg_adic) * mask_atendida
        df_final[f'KG_ADIC_{t_nome}'] = v_kg_adic * mask_atendida
        df_final[f'ADVAL_{t_nome}'] = adv * mask_atendida
        df_final[f'GRIS_{t_nome}'] = grs * mask_atendida
        df_final[f'EMEX_{t_nome}'] = emx * mask_atendida
        df_final[f'PEDAGIO_{t_nome}'] = ped * mask_atendida
        df_final[f'TAS_{t_nome}'] = get_v(m['taxas'].get("TAS")) * mask_atendida
        df_final[f'CTRC_{t_nome}'] = get_v(m['taxas'].get("CTRC")) * mask_atendida
        df_final[f'SUFRAMA_{t_nome}'] = get_v(m['taxas'].get("Suframa")) * mask_atendida
        df_final[f'SEC_CAT_{t_nome}'] = get_v(m['taxas'].get("SEC-CAT")) * mask_atendida
        df_final[f'FLUVIAL_{t_nome}'] = (valores_notas * get_v(m['taxas'].get("Fluvial"))) * mask_atendida
        df_final[f'REDESPACHO_F_{t_nome}'] = (valores_notas * get_v(m['taxas'].get("Redespacho Fluvial"))) * mask_atendida
        df_final[f'TDA_{t_nome}'] = np.maximum(valores_notas * get_v(m['taxas'].get("TDA %")), get_v(m['taxas'].get("TDA Min"))) * mask_atendida
        df_final[f'DESPACHO_{t_nome}'] = get_v(m['taxas'].get("Despacho")) * mask_atendida
        df_final[f'TRT_{t_nome}'] = trt * mask_atendida
        df_final[f'TOTAL_{t_nome}'] = frete_total
    return df_final

def to_excel(df_completo):
    output = BytesIO()
    cols_total = [c for c in df_completo.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    prefixos = ["PESO_BASE_", "KG_ADIC_", "ADVAL_", "GRIS_", "EMEX_", "PEDAGIO_", "TAS_", "CTRC_", "SUFRAMA_", "SEC_CAT_", "FLUVIAL_", "REDESPACHO_F_", "TDA_", "DESPACHO_", "TRT_", "OUTROS_", "TOTAL_"]
    cols_originais = [c for c in df_completo.columns if not any(c.startswith(p) for p in prefixos)]
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_geral = df_completo[cols_originais + cols_total].copy()
        df_geral.to_excel(writer, index=False, sheet_name='Geral')
        for t in transportadoras:
            cols_especificas = [c for c in df_completo.columns if c.endswith(f'_{t}')]
            df_t = df_completo[cols_originais + cols_especificas].copy()
            df_t.columns = [c.replace(f'_{t}', '') for c in df_t.columns]
            if 'TOTAL' in df_t.columns:
                cols_ordenadas = [c for c in df_t.columns if c != 'TOTAL'] + ['TOTAL']
                df_t = df_t[cols_ordenadas]
            df_t.to_excel(writer, index=False, sheet_name=t[:31])
    return output.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Ave Maria")
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
        with col_l2: st.image(st.session_state.logo_data, width=100)
        if st.button("✏️ Alterar Logo", use_container_width=True):
            st.session_state.logo_data = None
            st.rerun()
    else:
        up_logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg", "jpeg"])
        if up_logo:
            st.session_state.logo_data = up_logo.read()
            st.rerun()
    
    st.divider()
    st.markdown("""
        <style>
            [data-testid="stSidebarNav"] div[role="radiogroup"] > div:nth-child(5) label { display: none !important; }
            [data-testid="stSidebarNav"] div[role="radiogroup"] > div:nth-child(5)::before { content: ""; display: block; height: 1px; background-color: #4B4B4B; margin: 10px 0; width: 100%; }
            [data-testid="stSidebarNav"] div[role="radiogroup"] > div:nth-child(5) { pointer-events: none !important; }
        </style>
    """, unsafe_allow_html=True)

    menu_opcoes = ["📊 Dashboard", "🧮 Cotação", "🚛 Cadastro de Transportadora", "💰 Calculo de Comparativo", "📂 Base de Notas", "📜 Historico de Comparativos"]
    escolha = st.radio("Navegação", menu_opcoes)
    menu = escolha

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    st.markdown("""<style>span[data-baseweb="tag"] { background-color: #f1f5f9 !important; border: 1px solid #e2e8f0 !important; padding: 2px 8px !important; } </style>""", unsafe_allow_html=True)
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        df_hist = pd.DataFrame(res.data)
        all_dfs = []
        for _, r in df_hist.iterrows():
            if r['detalhes_json']:
                temp = pd.DataFrame(r['detalhes_json'])
                temp['id_referencia'] = r['id']
                all_dfs.append(temp)
        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            sel_tr = st.multiselect("🚛 Transportadoras", sorted(df_total['transportadora'].unique()), default=sorted(df_total['transportadora'].unique()))
            df_filt = df_total[df_total['transportadora'].isin(sel_tr)] if sel_tr else df_total
            if not df_filt.empty:
                df_unicos = df_filt.drop_duplicates(subset=['id_referencia', 'uf', 'mes_nf'])
                m1, m2, m3, m4 = st.columns(4)
                m1.markdown(f'<div class="metric-card"><div class="metric-label">NOTAS</div><div class="metric-value">{int(df_unicos["qtd"].sum())}</div></div>', unsafe_allow_html=True)
                m2.markdown(f'<div class="metric-card"><div class="metric-label">VALOR NOTAS</div><div class="metric-value">{format_brl(df_unicos["valor_total_notas"].sum())}</div></div>', unsafe_allow_html=True)
                m3.markdown(f'<div class="metric-card"><div class="metric-label">PESO</div><div class="metric-value">{format_kg(df_unicos["peso_total"].sum())}</div></div>', unsafe_allow_html=True)
                m4.markdown(f'<div class="metric-card"><div class="metric-label">INVESTIMENTO</div><div class="metric-value">{format_brl(df_filt["valor_total_frete"].sum())}</div></div>', unsafe_allow_html=True)
                st.subheader("💰 Melhor Custo por Estado")
                df_p = df_filt.pivot_table(index='uf', columns='transportadora', values='valor_total_frete', aggfunc='sum').fillna(0)
                st.dataframe(df_p.style.format(format_brl), use_container_width=True)
    else: st.info("Sem histórico disponível.")

# --- COTAÇÃO ---
elif menu == "🧮 Cotação":
    st.title("🧮 Cotação")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)
    if df_ts.empty: st.warning("Cadastre transportadoras.")
    else:
        with st.form("cota_avulsa"):
            c1, c2 = st.columns(2)
            cid = c1.text_input("Cidade")
            peso = c1.number_input("Peso", min_value=0.1, value=1.0)
            uf = c2.selectbox("UF", ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"], index=24)
            val = c2.number_input("Valor Nota", min_value=0.0)
            sel = st.multiselect("Transportadoras", df_ts['nome'].tolist())
            if st.form_submit_button("🚀 Calcular"):
                df_sim = pd.DataFrame([{"CIDADE": cid, "UF": uf, "PESO": peso, "VALOR": val}])
                res_calc = engine_calculo(df_sim, sel, df_ts)
                for t in sel:
                    v = res_calc[f'TOTAL_{t}'].iloc[0]
                    if v > 0: st.success(f"**{t}**: {format_brl(v)}")
                    else: st.error(f"**{t}**: Sem atendimento.")

# --- BASE DE NOTAS ---
elif menu == "📂 Base de Notas":
    st.title("📂 Gestão da Base")
    up = st.file_uploader("Excel", type=["xlsx"])
    if up and st.button("💾 Salvar"):
        df = pd.read_excel(up).fillna(0)
        supabase.table("base_comercial").delete().neq("id", 0).execute()
        supabase.table("base_comercial").insert({"dados_json": df.to_dict(orient='records')}).execute()
        st.success("Salvo!"); st.rerun()
    if st.button("🗑️ Limpar Base"): supabase.table("base_comercial").delete().neq("id", 0).execute(); st.rerun()

# --- CADASTRO ---
elif menu == "🚛 Cadastro de Transportadora":
    st.title("🚛 Cadastro")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    with st.expander("📝 Configurar", expanded=st.session_state.edit_id is not None):
        e_row = df_list[df_list['id'] == st.session_state.edit_id].iloc[0] if st.session_state.edit_id else None
        nome = st.text_input("Nome", value=e_row['nome'] if e_row is not None else "").upper()
        c1, c2 = st.columns(2)
        f_t = c1.file_uploader("Tabela", type=["xlsx"])
        f_a = c2.file_uploader("Abrangência", type=["xlsx"])
        df_t = pd.read_excel(f_t).fillna(0) if f_t else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_a).fillna(0) if f_a else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)
        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + list(df_t.columns.astype(str))
            cols_a = ["Não mapear"] + list(df_a.columns.astype(str))
            m_tb_sig = st.selectbox("Sigla Tabela", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
            m_ap_cid = st.selectbox("Cidade Abrangência", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
            m_ap_sig = st.selectbox("Sigla Abrangência", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            n_f = st.number_input("Faixas", 1, 50, len(mapa.get('faixas', [])) or 1)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({"min": r[0].number_input("De", value=float(f_i.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input("Até", value=float(f_i.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox("Coluna", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")})
            if st.button("💾 Salvar"):
                payload = {"nome": nome, "tabela_json": df_t.to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "faixas": faixas, "taxas": mapa.get('taxas', {}), "kg_extra": mapa.get('kg_extra', "Não mapear")}}
                if st.session_state.edit_id: supabase.table("transportadoras").update(payload).eq("id", st.session_state.edit_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.rerun()
    for _, r in df_list.iterrows():
        c = st.columns([8, 1, 1]); c[0].write(r['nome'])
        if c[1].button("✏️", key=f"e{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
        if c[2].button("🗑️", key=f"d{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- CALCULO COMPARATIVO ---
elif menu == "💰 Calculo de Comparativo":
    st.title("💰 Comparativo")
    res_b = supabase.table("base_comercial").select("*").execute()
    res_t = supabase.table("transportadoras").select("*").execute()
    if res_b.data and res_t.data:
        df_base = pd.DataFrame(res_b.data[0]['dados_json'])
        sel = st.multiselect("Transportadoras", [t['nome'] for t in res_t.data])
        if sel and st.button("🚀 Calcular"):
            df_calc = engine_calculo(df_base, sel, pd.DataFrame(res_t.data))
            resumo = []
            for t in sel:
                resumo.append({"transportadora": t, "uf": "GERAL", "qtd": len(df_base), "valor_total_notas": df_base.iloc[:, 7].sum(), "peso_total": df_base.iloc[:, 6].sum(), "valor_total_frete": df_calc[f'TOTAL_{t}'].sum()})
            supabase.table("cotacoes").insert({"data_hora": (datetime.now()-timedelta(hours=3)).strftime("%d/%m/%Y %H:%M"), "qtd": len(df_base), "detalhes_json": resumo}).execute()
            st.success("Calculado!"); st.rerun()

# --- HISTORICO ---
elif menu == "📜 Historico de Comparativos":
    st.title("📜 Histórico")
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    if res_h.data:
        for r in res_h.data:
            with st.expander(f"📅 {r['data_hora']} | 📦 {r['qtd']} Notas"):
                st.write(pd.DataFrame(r['detalhes_json']))
                # FUNÇÃO DE EXCLUSÃO REESTABELECIDA
                if st.button("🗑️ Excluir Comparativo", key=f"del_hist_{r['id']}"):
                    supabase.table("cotacoes").delete().eq("id", r['id']).execute()
                    st.success("Excluído com sucesso!")
                    st.rerun()
