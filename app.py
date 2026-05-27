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

# MOTOR DE CÁLCULO
def engine_calculo(df_base, selecionadas, df_ts):
    df_final = df_base.copy()
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
        
        dic_ponte = {
            (row['cid_clean'], row['uf_clean']): super_limpeza(row[m['ap_sigla']]) 
            for _, row in df_abr.iterrows()
        }
        
        siglas_match = []
        for c, u in zip(cid_notas, uf_notas):
            siglas_match.append(dic_ponte.get((c, u), "ND"))
        siglas_match = np.array(siglas_match)

        df_tab['sig_clean'] = df_tab[m['tab_sigla']].astype(str).apply(super_limpeza)
        df_tab_idx = df_tab.set_index('sig_clean')
        
        def get_v(col): 
            if col and col != "Não mapear" and col in df_tab_idx.columns:
                return df_tab_idx[col].reindex(siglas_match).fillna(0).values
            return np.zeros(len(df_base))
        
        f_peso = np.zeros(len(df_base)); v_kg_adic = np.zeros(len(df_base))
        mask_atendida = (siglas_match != "ND")
        
        for faixa in m['faixas']:
            v_f = get_v(faixa['col'])
            mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0) & mask_atendida
            f_peso[mask] = v_f[mask]
            
        u_max = m['faixas'][-1]['max']
        mask_e = (pesos_notas > u_max) & mask_atendida
        if mask_e.any():
            v_b = get_v(m['faixas'][-1]['col']); v_ex = get_v(m['kg_extra'])
            v_kg_adic[mask_e] = (pesos_notas[mask_e] - u_max) * v_ex[mask_e]
            f_peso[mask_e] = v_b[mask_e] + v_kg_adic[mask_e]
        
        adv = np.maximum(valores_notas * get_v(m['taxas'].get("Ad Valorem %")), get_v(m['taxas'].get("Ad Valorem Min")))
        grs = np.maximum(valores_notas * get_v(m['taxas'].get("Gris %")), get_v(m['taxas'].get("Gris Min")))
        emx = np.maximum(valores_notas * get_v(m['taxas'].get("Emex %")), get_v(m['taxas'].get("Emex Min")))
        ped = np.ceil(pesos_notas/100) * get_v(m['taxas'].get("Pedagio"))
        suf = get_v(m['taxas'].get("Suframa"))
        seccat = get_v(m['taxas'].get("SEC-CAT"))
        fluv = valores_notas * get_v(m['taxas'].get("Fluvial"))
        red_f = valores_notas * get_v(m['taxas'].get("Redespacho Fluvial"))
        tda = np.maximum(valores_notas * get_v(m['taxas'].get("TDA %")), get_v(m['taxas'].get("TDA Min")))
        tde = np.maximum(valores_notas * get_v(m['taxas'].get("TDE %")), get_v(m['taxas'].get("TDE Min")))
        despacho = get_v(m['taxas'].get("Despacho"))
        
        frete_parcial = (f_peso + adv + grs + emx + ped + get_v(m['taxas'].get("TAS")) + get_v(m['taxas'].get("CTRC")) + suf + seccat + fluv + red_f + tda + tde + despacho)
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
        df_final[f'SUFRAMA_{t_nome}'] = suf * mask_atendida
        df_final[f'SEC_CAT_{t_nome}'] = seccat * mask_atendida
        df_final[f'FLUVIAL_{t_nome}'] = fluv * mask_atendida
        df_final[f'REDESPACHO_F_{t_nome}'] = red_f * mask_atendida
        df_final[f'TDA_{t_nome}'] = tda * mask_atendida
        df_final[f'TDE_{t_nome}'] = tde * mask_atendida
        df_final[f'DESPACHO_{t_nome}'] = despacho * mask_atendida
        df_final[f'TRT_{t_nome}'] = trt * mask_atendida
        df_final[f'TOTAL_{t_nome}'] = frete_total
    return df_final

def to_excel(df_completo):
    output = BytesIO()
    cols_total = [c for c in df_completo.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    prefixos = ["PESO_BASE_", "KG_ADIC_", "ADVAL_", "GRIS_", "EMEX_", "PEDAGIO_", "TAS_", "CTRC_", "SUFRAMA_", "SEC_CAT_", "FLUVIAL_", "REDESPACHO_F_", "TDA_", "TDE_", "DESPACHO_", "TRT_", "OUTROS_", "TOTAL_"]
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

# --- SIDEBAR ATUALIZADA ---
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
            [data-testid="stSidebarNav"] div[role="radiogroup"] > div:nth-child(5) label {
                display: none !important;
            }
            [data-testid="stSidebarNav"] div[role="radiogroup"] > div:nth-child(5)::before {
                content: "";
                display: block;
                height: 1px;
                background-color: #4B4B4B;
                margin: 10px 0;
                width: 100%;
            }
            [data-testid="stSidebarNav"] div[role="radiogroup"] > div:nth-child(5) {
                pointer-events: none !important;
            }
        </style>
    """, unsafe_allow_html=True)

    menu_opcoes = [
        "📊 Dashboard", 
        "🧮 Cotação", 
        "🚛 Cadastro de Transportadora", 
        "💰 Calculo de Comparativo",
        "📂 Base de Notas", 
        "📜 Historico de Comparativos"
    ]
    escolha = st.radio("Navegação", menu_opcoes)
    menu = "📊 Dashboard" if escolha == "---" else escolha

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    st.markdown("""
        <style>
        span[data-baseweb="tag"] { background-color: #f1f5f9 !important; border: 1px solid #e2e8f0 !important; border-radius: 6px !important; padding: 2px 8px !important; }
        span[data-baseweb="tag"] span { color: #475569 !important; font-size: 12px !important; }
        div[data-testid="column"] { padding: 0 10px !important; }
        </style>
    """, unsafe_allow_html=True)

    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        df_historico_base = pd.DataFrame(res.data)
        all_dfs = []
        for _, r in df_historico_base.iterrows():
            if r['detalhes_json']:
                temp_df = pd.DataFrame(r['detalhes_json'])
                temp_df['id_referencia'] = r['id']
                all_dfs.append(temp_df)

        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            nomes_t = sorted(df_total['transportadora'].unique()) if 'transportadora' in df_total.columns else []
            col_uf = next((c for c in df_total.columns if c.upper() == 'UF'), None)
            lista_ufs = sorted(df_total[col_uf].unique()) if col_uf else []

            with st.container():
                f1, f2 = st.columns([2, 2])
                sel_tr = f1.multiselect("🚛 Transportadoras", nomes_t, default=nomes_t)
                sel_uf = f2.multiselect("📍 Estados (UF)", lista_ufs, default=lista_ufs)
            
            df_filt = df_total.copy()
            if sel_tr: df_filt = df_filt[df_filt['transportadora'].isin(sel_tr)]
            if col_uf and sel_uf: df_filt = df_filt[df_filt[col_uf].isin(sel_uf)]
            
            if not df_filt.empty:
                df_unicos = df_filt.drop_duplicates(subset=['id_referencia', 'uf', 'mes_nf'])
                qtd_notas = df_unicos['qtd'].sum()
                val_total_notas = df_unicos['valor_total_notas'].sum()
                peso_total = df_unicos['peso_total'].sum()
                val_total_frete = df_filt['valor_total_frete'].sum()
                
                st.markdown("<br>", unsafe_allow_html=True)
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.markdown(f'<div class="metric-card"><div class="metric-label">NOTAS PROCESSADAS</div><div class="metric-value">{int(qtd_notas)}</div></div>', unsafe_allow_html=True)
                with m2: st.markdown(f'<div class="metric-card"><div class="metric-label">VALOR TOTAL NOTAS</div><div class="metric-value">{format_brl(val_total_notas)}</div></div>', unsafe_allow_html=True)
                with m3: st.markdown(f'<div class="metric-card"><div class="metric-label">PESO TOTAL</div><div class="metric-value">{format_kg(peso_total)}</div></div>', unsafe_allow_html=True)
                with m4: st.markdown(f'<div class="metric-card"><div class="metric-label">INVESTIMENTO EM FRETE</div><div class="metric-value">{format_brl(val_total_frete)}</div></div>', unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.subheader("💰 Melhor Custo por Estado")
                if col_uf:
                    df_pivot = df_filt.pivot_table(index=col_uf, columns='transportadora', values='valor_total_frete', aggfunc='sum').fillna(0)
                    def highlight_min_no_zero(s):
                        s_validos = s[s > 0]
                        is_min = s == s_validos.min() if not s_validos.empty else [False]*len(s)
                        return ['background-color: #ecfdf5; color: #065f46; font-weight: bold; border: 1px solid #10b981' if v else 'color: #475569' for v in is_min]
                    st.dataframe(df_pivot.style.apply(highlight_min_no_zero, axis=1).format(format_brl), use_container_width=True, height=500)
    else: 
        st.info("Sem histórico de cotações para exibir.")

# --- COTAÇÃO ---
elif menu == "🧮 Cotação":
    st.title("🧮 Cotação")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)
    if df_ts.empty:
        st.warning("Nenhuma transportadora cadastrada.")
    else:
        with st.form("form_calculadora_avulsa"):
            col1, col2 = st.columns(2)
            with col1:
                cid_input = st.text_input("Cidade de Destino", placeholder="Ex: RIO DE JANEIRO")
                peso_input = st.number_input("Peso Total (kg)", min_value=0.1, value=1.0, step=0.5)
            with col2:
                uf_input = st.selectbox("UF", ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"], index=18)
                valor_input = st.number_input("Valor da Nota (R$)", min_value=0.0, value=0.0, step=100.0)
            transp_selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
            submit = st.form_submit_button("🚀 Calcular Frete")

        if submit:
            if not cid_input or not transp_selecionadas:
                st.error("Preencha os campos obrigatórios.")
            else:
                df_simulado = pd.DataFrame([{"CIDADE": cid_input, "UF": uf_input, "PESO": peso_input, "VALOR": valor_input}])
                with st.spinner("Calculando..."):
                    try:
                        res_calc = engine_calculo(df_simulado, transp_selecionadas, df_ts)
                        st.subheader("🏁 Comparativo de Preços")
                        ranking = []
                        for t in transp_selecionadas:
                            col_total = f'TOTAL_{t}'
                            if col_total in res_calc.columns:
                                valor_total = res_calc[col_total].iloc[0]
                                ranking.append({"transp": t, "total": valor_total})
                        ranking = sorted(ranking, key=lambda x: x['total'] if x['total'] > 0 else 999999)

                        mapeamento_taxas = {
                            "PESO_BASE": "Frete Peso", "KG_ADIC": "KG Adicional", "ADVAL": "Ad Valorem", "GRIS": "Gris", "EMEX": "Emex",
                            "PEDAGIO": "Pedágio", "TAS": "TAS", "CTRC": "CTRC", "SUFRAMA": "Suframa", "SEC_CAT": "SEC-CAT",
                            "FLUVIAL": "Fluvial", "REDESPACHO_F": "Redespacho Fluv.", "TDA": "TDA", "TDE": "TDE", "DESPACHO": "Despacho", "TRT": "TRT"
                        }
                        for item in ranking:
                            t_nome = item['transp']
                            if item['total'] > 0:
                                st.markdown(f"""
                                <div style="background-color: #ffffff; padding: 8px 15px; border-radius: 8px; border-left: 4px solid #10b981; margin-bottom: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center;">
                                    <div><span style="color: #64748b; font-size: 0.65rem; font-weight: bold; text-transform: uppercase;">Transportadora</span><br><b style="font-size: 0.9rem; color: #1e293b;">{t_nome}</b></div>
                                    <div style="text-align: right;"><span style="color: #64748b; font-size: 0.65rem; font-weight: bold; text-transform: uppercase;">Total</span><br><b style="font-size: 1.1rem; color: #059669;">{format_brl(item['total'])}</b></div>
                                </div>""", unsafe_allow_html=True)
                                detalhes_exibir = []
                                for col_key, label in mapeamento_taxas.items():
                                    col_full = f"{col_key}_{t_nome}"
                                    if col_full in res_calc.columns:
                                        v = res_calc[col_full].iloc[0]
                                        if v > 0:
                                            if col_key in ["PESO_BASE", "KG_ADIC"]: detalhes_exibir.append(f"<div style='font-size: 0.85rem; color: #1e293b;'><b>{label}: {format_brl(v)}</b></div>")
                                            else: detalhes_exibir.append(f"<div style='font-size: 0.8rem; color: #475569;'>{label}: {format_brl(v)}</div>")
                                if detalhes_exibir:
                                    with st.expander(f"🔍 Taxas - {t_nome}"):
                                        for linha in detalhes_exibir: st.markdown(linha, unsafe_allow_html=True)
                                        st.markdown(f"<hr style='margin: 5px 0;'><b style='font-size: 0.85rem;'>Final: {format_brl(item['total'])}</b>", unsafe_allow_html=True)
                            else: st.warning(f"🚫 {t_nome}: Sem atendimento.")
                    except Exception as e: st.error(f"Erro no cálculo: {e}")

# --- BASE DE NOTAS ---
elif menu == "📂 Base de Notas":
    st.title("📂 Gestão da Base de Notas")
    up_base = st.file_uploader("Subir Base de Notas (Excel)", type=["xlsx"])
    if up_base:
        if st.button("💾 Salvar Base no Sistema"):
            df_base_nova = pd.read_excel(up_base).fillna(0)
            supabase.table("base_comercial").delete().neq("id", 0).execute()
            supabase.table("base_comercial").insert({"dados_json": df_base_nova.to_dict(orient='records')}).execute()
            st.success("Base de Notas salva com sucesso!"); st.rerun()
    res_b = supabase.table("base_comercial").select("id").execute()
    if res_b.data:
        st.info("✅ Existe uma base carregada e pronta para o cálculo.")
        if st.button("🗑️ Limpar Base Atual"):
            supabase.table("base_comercial").delete().neq("id", 0).execute(); st.rerun()

# --- CADASTRO ---
elif menu == "🚛 Cadastro de Transportadora":
    st.title("🚛 Cadastro de Transportadora")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)
    if 'form_reset_key' not in st.session_state: st.session_state.form_reset_key = 0
    with st.expander("📝 Configurar Mapeamento", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id is not None and not df_list.empty else None
        nome_t = st.text_input("Nome", value=e_row['nome'] if e_row is not None else "", key=f"n_{st.session_state.form_reset_key}").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("📂 Tabela de Preços", type=["xlsx"], key=f"t_{st.session_state.form_reset_key}")
        f_abr = c2.file_uploader("📂 Relação de Cidades (Siglas)", type=["xlsx"], key=f"a_{st.session_state.form_reset_key}")
        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)
        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]
            cm1, cm2 = st.columns(2)
            with cm1:
                st.markdown("### 📋 Configuração Tabela")
                m_tb_sig = st.selectbox("Coluna Sigla (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
                m_tb_uf = st.selectbox("Coluna UF (na Tabela)", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)
                col_kg_ex = st.selectbox("Coluna Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            with cm2:
                st.markdown("### 📍 Relação de Cidades")
                m_ap_cid = st.selectbox("Coluna Cidade (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
                m_ap_uf = st.selectbox("Coluna UF (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_uf')) if mapa.get('ap_uf') in cols_a else 0)
                m_ap_sig = st.selectbox("Coluna Sigla (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            st.divider(); st.markdown("### ⚖️ Mapeamento de Faixas de Peso")
            n_f = st.number_input("Qtd Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({"min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")})
            st.divider(); st.markdown("### 💰 Mapeamento de Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "Suframa", "SEC-CAT", "Fluvial", "Redespacho Fluvial", "TDA %", "TDA Min", "TDE %", "TDE Min", "Despacho", "TRT %"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0, key=f"tx_{idx}")
            if st.button("💾 Salvar Transportadora"):
                payload = {"nome": nome_t, "tabela_json": df_t.to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": {"ap_cidade": m_ap_cid, "ap_uf": m_ap_uf, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.session_state.form_reset_key += 1; st.rerun()
    if not df_list.empty:
        for _, r in df_list.iterrows():
            c = st.columns([7, 1, 1]); c[0].write(f"**{r['nome']}**")
            if c[1].button("✏️", key=f"ed{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
            if c[2].button("🗑️", key=f"dl{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- CALCULO DE COMPARATIVO ---
elif menu == "💰 Calculo de Comparativo":
    st.title("💰 Cotação de Fretes")
    res_base = supabase.table("base_comercial").select("*").execute()
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)
    if res_base.data and not df_ts.empty:
        df_base = pd.DataFrame(res_base.data[0]['dados_json'])
        st.info(f"Utilizando Base de Notas salva: {len(df_base)} notas.")
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Processando indicadores..."):
                df_calc = engine_calculo(df_base, selecionadas, df_ts)
                data_sp = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")
                col_uf = next((c for c in df_base.columns if c.upper() == 'UF'), 'UF')
                col_val_nf = next((c for c in df_base.columns if 'VALOR' in c.upper() and 'FRETE' not in c.upper()), df_base.columns[7])
                col_peso = next((c for c in df_base.columns if 'PESO' in c.upper() and 'BASE' not in c.upper()), df_base.columns[6])
                col_data_nf = next((c for c in df_base.columns if 'DATA' in c.upper() or 'EMISSAO' in c.upper()), None)
                meses_br = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
                resumo_final = []
                for t in selecionadas:
                    agrupadores = [col_uf]
                    if col_data_nf:
                        df_calc['__temp_mes'] = pd.to_datetime(df_calc[col_data_nf], errors='coerce').dt.month.map(lambda x: meses_br[int(x)-1] if pd.notna(x) else "Indefinido")
                        agrupadores.append('__temp_mes')
                    res_uf = df_calc.groupby(agrupadores).agg({col_val_nf: 'sum', col_peso: 'sum', f'TOTAL_{t}': 'sum'}).reset_index()
                    qtd_uf = df_calc.groupby(agrupadores).size().reset_index(name='qtd')
                    res_uf = res_uf.merge(qtd_uf, on=agrupadores)
                    for _, row in res_uf.iterrows():
                        resumo_final.append({
                            "transportadora": t, "uf": row[col_uf], "mes_nf": row['__temp_mes'] if col_data_nf else meses_br[datetime.now().month-1],
                            "qtd": int(row['qtd']), "valor_total_notas": float(row[col_val_nf]), "peso_total": float(row[col_peso]),
                            "valor_total_frete": float(row[f'TOTAL_{t}']), "lista_t": selecionadas
                        })
                supabase.table("cotacoes").insert({"data_hora": data_sp, "qtd": len(df_base), "detalhes_json": resumo_final}).execute()
                st.success("Cálculo finalizado!"); st.rerun()
    else: st.warning("Cadastre a Base de Notas e as Transportadoras.")

# --- HISTORICO DE COMPARATIVOS ---
elif menu == "📜 Historico de Comparativos":
    st.title("📜 Historico de Comparativos")
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    
    # Buscamos a base e as transportadoras atuais para refazer o cálculo em tempo real
    res_base = supabase.table("base_comercial").select("*").execute()
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts_atual = pd.DataFrame(res_t.data)

    if res_h.data:
        for r in res_h.data:
            dt, detalhes, qtd_total_h = r['data_hora'], r['detalhes_json'], r['qtd']
            total_frete_h = sum(item['valor_total_frete'] for item in detalhes)
            
            with st.expander(f"📅 {dt}  |  📦 {qtd_total_h} Notas  |  💰 {format_brl(total_frete_h)}"):
                # O 'detalhes_json' aqui serve apenas para o resumo visual do expander
                df_h_resumo = pd.DataFrame(detalhes)
                transportadoras_na_epoca = df_h_resumo['transportadora'].unique().tolist()
                
                st.markdown("### Resumo do Comparativo")
                consolidado_t = df_h_resumo.groupby('transportadora')['valor_total_frete'].sum().reset_index()
                for _, row_t in consolidado_t.iterrows():
                    st.write(f"**{row_t['transportadora']}**: {format_brl(row_t['valor_total_frete'])}")
                
                st.divider()
                
                c_btn_down, c_btn_del = st.columns([0.7, 0.3])
                
                with c_btn_down:
                    if not res_base.data:
                        st.warning("Base de notas original não encontrada para processar.")
                    else:
                        # RE-CÁLCULO EM TEMPO REAL PARA O EXCEL DETALHADO
                        if st.button("📥 Exportar Excel", key=f"gen_{r['id']}", use_container_width=True):
                            with st.spinner("Processando dados..."):
                                try:
                                    # 1. Recupera a base de notas
                                    df_base_original = pd.DataFrame(res_base.data[0]['dados_json'])
                                    
                                    # 2. Roda o motor de cálculo novamente (gera todas as taxas/colunas)
                                    df_detalhado = engine_calculo(df_base_original, transportadoras_na_epoca, df_ts_atual)
                                    
                                    # 3. Gera o arquivo usando sua função to_excel (que cria a aba Geral e as abas por Transp)
                                    excel_bin = to_excel(df_detalhado)
                                    
                                    # 4. Oferece o download (usamos um state para mostrar o link após processar)
                                    st.download_button(
                                        label="✅ Arquivo Pronto! Clique para Baixar",
                                        data=excel_bin,
                                        file_name=f"Comparativo_Detalhado_{dt.replace('/', '-').replace(':', 'h')}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        key=f"dl_real_{r['id']}",
                                        use_container_width=True
                                    )
                                except Exception as e:
                                    st.error(f"Erro ao processar: {e}")
                
                with c_btn_del:
                    if st.button("🗑️ Excluir", key=f"del_h_{r['id']}", use_container_width=True):
                        supabase.table("cotacoes").delete().eq("id", r['id']).execute()
                        st.rerun()
    else:
        st.info("Nenhum histórico de comparativos encontrado.")
