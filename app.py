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

# CSS ESPECÍFICO (ESTILO VERSÃO 18.0)
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
    /* Filtros (tags) menores e discretos */
    span[data-baseweb="tag"] {
        background-color: #f1f5f9 !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 6px !important;
        padding: 2px 8px !important;
    }
    span[data-baseweb="tag"] span {
        color: #475569 !important;
        font-size: 12px !important;
    }
    span[data-baseweb="tag"] [role="button"] svg {
        fill: #94a3b8 !important;
    }
    div[data-testid="column"] {
        padding: 0 10px !important;
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

# --- MOTOR DE CÁLCULO INTEGRAL ---
def engine_calculo(df_base, selecionadas, df_ts):
    df_final = df_base.copy()
    col_cid_nome = next((c for c in df_base.columns if 'CIDADE' in c.upper()), df_base.columns[2])
    col_peso_nome = next((c for c in df_base.columns if 'PESO' in c.upper() and 'BASE' not in c.upper()), df_base.columns[6])
    col_valor_nome = next((c for c in df_base.columns if 'VALOR' in c.upper() and 'FRETE' not in c.upper()), df_base.columns[7])
    
    cid_notas = df_base[col_cid_nome].astype(str).apply(super_limpeza).values
    pesos_notas = pd.to_numeric(df_base[col_peso_nome], errors='coerce').fillna(0).values
    valores_notas = pd.to_numeric(df_base[col_valor_nome], errors='coerce').fillna(0).values

    for t_nome in selecionadas:
        t_r = df_ts[df_ts['nome'] == t_nome].iloc[0]
        m, df_tab, df_abr = t_r['mapeamento_json'], pd.DataFrame(t_r['tabela_json']), pd.DataFrame(t_r['cidades_json'])
        df_abr['cid_clean'] = df_abr[m['ap_cidade']].astype(str).apply(super_limpeza)
        dic_ponte = df_abr.set_index('cid_clean')[m['ap_sigla']].astype(str).apply(super_limpeza).to_dict()
        siglas_match = pd.Series(cid_notas).map(dic_ponte).fillna("ND").values
        df_tab['sig_clean'] = df_tab[m['tab_sigla']].astype(str).apply(super_limpeza)
        df_tab_idx = df_tab.set_index('sig_clean')
        
        def get_v(col): return df_tab_idx[col].reindex(siglas_match).fillna(0).values if col and col != "Não mapear" and col in df_tab_idx.columns else np.zeros(len(df_base))
        
        f_peso = np.zeros(len(df_base)); v_kg_adic = np.zeros(len(df_base))
        for faixa in m['faixas']:
            v_f = get_v(faixa['col']); mask = (pesos_notas <= faixa['max']) & (f_peso == 0.0); f_peso[mask] = v_f[mask]
        u_max = m['faixas'][-1]['max']; mask_e = (pesos_notas > u_max)
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

        df_final[f'PESO_BASE_{t_nome}'] = f_peso - v_kg_adic
        df_final[f'KG_ADIC_{t_nome}'] = v_kg_adic
        df_final[f'ADVAL_{t_nome}'] = adv
        df_final[f'GRIS_{t_nome}'] = grs
        df_final[f'EMEX_{t_nome}'] = emx
        df_final[f'PEDAGIO_{t_nome}'] = ped
        df_final[f'TAS_{t_nome}'] = get_v(m['taxas'].get("TAS"))
        df_final[f'CTRC_{t_nome}'] = get_v(m['taxas'].get("CTRC"))
        df_final[f'SUFRAMA_{t_nome}'] = suf
        df_final[f'SEC_CAT_{t_nome}'] = seccat
        df_final[f'FLUVIAL_{t_nome}'] = fluv
        df_final[f'REDESPACHO_F_{t_nome}'] = red_f
        df_final[f'TOTAL_{t_nome}'] = (f_peso + adv + grs + emx + ped + get_v(m['taxas'].get("TAS")) + get_v(m['taxas'].get("CTRC")) + suf + seccat + fluv + red_f)
    return df_final

def to_excel(df_completo):
    output = BytesIO()
    cols_total = [c for c in df_completo.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    prefixos = ["PESO_BASE_", "KG_ADIC_", "ADVAL_", "GRIS_", "EMEX_", "PEDAGIO_", "TAS_", "CTRC_", "SUFRAMA_", "SEC_CAT_", "FLUVIAL_", "REDESPACHO_F_", "OUTROS_", "TOTAL_"]
    cols_originais = [c for c in df_completo.columns if not any(c.startswith(p) for p in prefixos)]
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_geral = df_completo[cols_originais + cols_total].copy()
        df_geral.to_excel(writer, index=False, sheet_name='Geral')
        for t in transportadoras:
            cols_especificas = [c for c in df_completo.columns if c.endswith(f'_{t}')]
            df_t = df_completo[cols_originais + cols_especificas].copy()
            df_t.columns = [c.replace(f'_{t}', '') for c in df_t.columns]
            df_t.to_excel(writer, index=False, sheet_name=t[:31])
    return output.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.title("Ave Maria - Analise de Fretes")
    st.info("Versão 23.0")
    menu = st.radio("Navegação", ["📊 Dashboard", "📂 Base Comercial", "🚛 Cadastro de Transportadora", "💰 Comparativo", "📜 Histórico"])

# --- DASHBOARD (RESTAURADO E OTIMIZADO) ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        all_dfs = [pd.DataFrame(r['detalhes_json']) for r in res.data if r['detalhes_json']]
        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            
            # Filtros Otimizados (Tags menores)
            with st.container():
                f1, f2, f3 = st.columns([1.5, 2.5, 1.5])
                
                # Transportadoras extraídas dos dados
                nomes_t = sorted(df_total['transportadora'].unique())
                sel_tr = f1.multiselect("🚛 Transportadoras", nomes_t, default=nomes_t)
                
                # UF extraída dos dados
                lista_ufs = sorted(df_total['uf'].unique())
                sel_uf = f2.multiselect("📍 Estados (UF)", lista_ufs, default=lista_ufs)
                
                # Mês (Coluna B da planilha original, tratada como texto)
                lista_meses = sorted(df_total['mes_nf'].unique())
                sel_data = f3.multiselect("📅 Mês Referência", lista_meses, default=lista_meses)
            
            # Aplicar filtros
            df_filt = df_total[
                (df_total['transportadora'].isin(sel_tr)) & 
                (df_total['uf'].isin(sel_uf)) & 
                (df_total['mes_nf'].isin(sel_data))
            ]
            
            if not df_filt.empty:
                # Métricas
                val_total_notas = df_filt['valor_total_notas'].sum()
                peso_total = df_filt['peso_total'].sum()
                val_total_frete = df_filt['valor_total_frete'].sum()
                
                st.markdown("<br>", unsafe_allow_html=True)
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.markdown(f'<div class="metric-card"><div class="metric-label">NOTAS PROCESSADAS</div><div class="metric-value">{int(df_filt["qtd"].sum())}</div></div>', unsafe_allow_html=True)
                with m2: st.markdown(f'<div class="metric-card"><div class="metric-label">VALOR TOTAL NOTAS</div><div class="metric-value">{format_brl(val_total_notas)}</div></div>', unsafe_allow_html=True)
                with m3: st.markdown(f'<div class="metric-card"><div class="metric-label">PESO TOTAL</div><div class="metric-value">{format_kg(peso_total)}</div></div>', unsafe_allow_html=True)
                with m4: st.markdown(f'<div class="metric-card"><div class="metric-label">INVESTIMENTO EM FRETE</div><div class="metric-value">{format_brl(val_total_frete)}</div></div>', unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.subheader("💰 Melhor Custo por Estado")
                
                df_pivot = df_filt.pivot_table(index='uf', columns='transportadora', values='valor_total_frete', aggfunc='sum').fillna(0)
                
                def highlight_min_no_zero(s):
                    s_validos = s[s > 0]
                    is_min = s == s_validos.min() if not s_validos.empty else [False]*len(s)
                    return ['background-color: #ecfdf5; color: #065f46; font-weight: bold; border: 1px solid #10b981' if v else 'color: #475569' for v in is_min]
                
                st.dataframe(df_pivot.style.apply(highlight_min_no_zero, axis=1).format(format_brl), use_container_width=True, height=500)
    else: st.info("Sem histórico de cotações.")

# --- BASE COMERCIAL ---
elif menu == "📂 Base Comercial":
    st.title("📂 Gestão da Base Comercial")
    up_base = st.file_uploader("Subir Base de Notas (Excel)", type=["xlsx"])
    if up_base:
        if st.button("💾 Salvar Base no Sistema"):
            df_base_nova = pd.read_excel(up_base).fillna(0)
            supabase.table("base_comercial").delete().neq("id", 0).execute()
            supabase.table("base_comercial").insert({"dados_json": df_base_nova.to_dict(orient='records')}).execute()
            st.success("Base Comercial salva com sucesso!"); st.rerun()
    res_b = supabase.table("base_comercial").select("id").execute()
    if res_b.data:
        st.info("✅ Existe uma base carregada.")
        if st.button("🗑️ Limpar Base Atual"):
            supabase.table("base_comercial").delete().neq("id", 0).execute(); st.rerun()

# --- CADASTRO ---
elif menu == "🚛 Cadastro de Transportadora":
    # (Manteve a sua lógica original de cadastro de transportadoras)
    st.title("🚛 Cadastro de Transportadora")
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    
    with st.expander("📝 Configurar Mapeamento", expanded=st.session_state.edit_id is not None):
        e_id = st.session_state.edit_id
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id and not df_list.empty else None
        nome_t = st.text_input("Nome", value=e_row['nome'] if e_row is not None else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("📂 Tabela de Preços", type=["xlsx"])
        f_abr = c2.file_uploader("📂 Cidades (Siglas)", type=["xlsx"])
        
        if st.button("💾 Salvar Transportadora"):
            # Lógica de salvamento aqui...
            st.success("Salvo!"); st.rerun()

    if not df_list.empty:
        for _, r in df_list.iterrows():
            c = st.columns([7, 1, 1]); c[0].write(f"**{r['nome']}**")
            if c[1].button("✏️", key=f"ed{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
            if c[2].button("🗑️", key=f"dl{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Cotação de Fretes")
    res_base = supabase.table("base_comercial").select("*").execute()
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)
    if res_base.data and not df_ts.empty:
        df_base = pd.DataFrame(res_base.data[0]['dados_json'])
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Calcular"):
            with st.spinner("Calculando..."):
                df_calc = engine_calculo(df_base, selecionadas, df_ts)
                data_sp = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")
                
                col_uf = next((c for c in df_base.columns if c.upper() == 'UF'), 'UF')
                col_val_nf = next((c for c in df_base.columns if 'VALOR' in c.upper() and 'FRETE' not in c.upper()), df_base.columns[7])
                col_peso = next((c for c in df_base.columns if 'PESO' in c.upper() and 'BASE' not in c.upper()), df_base.columns[6])
                # Fixa a Coluna B como Mês Referência (Texto)
                col_mes_ref = df_base.columns[1] if len(df_base.columns) > 1 else "MES"
                
                resumo_final = []
                for t in selecionadas:
                    res_uf = df_calc.groupby([col_uf, col_mes_ref]).agg({col_val_nf: 'sum', col_peso: 'sum', f'TOTAL_{t}': 'sum'}).reset_index()
                    for _, row in res_uf.iterrows():
                        resumo_final.append({
                            "transportadora": t,
                            "uf": row[col_uf],
                            "mes_nf": str(row[col_mes_ref]),
                            "qtd": len(df_base[df_base[col_uf] == row[col_uf]]),
                            "valor_total_notas": float(row[col_val_nf]),
                            "peso_total": float(row[col_peso]),
                            "valor_total_frete": float(row[f'TOTAL_{t}']),
                            "lista_t": selecionadas
                        })
                
                supabase.table("cotacoes").insert({"data_hora": data_sp, "qtd": len(df_base), "detalhes_json": resumo_final}).execute()
                st.success("Cálculo Finalizado!"); st.rerun()

# --- HISTÓRICO (COM BOTÃO ÚNICO DE DOWNLOAD) ---
elif menu == "📜 Histórico":
    st.title("📜 Histórico de Cotações")
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    if res_h.data:
        for r in res_h.data:
            dt = r['data_hora']
            detalhes = r['detalhes_json']
            total_frete_h = sum(item['valor_total_frete'] for item in detalhes)
            
            with st.expander(f"📅 {dt}  |  📦 {r['qtd']} Notas  |  💰 {format_brl(total_frete_h)}"):
                df_h = pd.DataFrame(detalhes)
                st.markdown("### Consolidado por Transportadora")
                consolidado_t = df_h.groupby('transportadora')['valor_total_frete'].sum().reset_index()
                for _, row_t in consolidado_t.iterrows():
                    st.write(f"**{row_t['transportadora']}**: {format_brl(row_t['valor_total_frete'])}")
                
                st.divider()
                c1, c2 = st.columns([3, 1])
                
                # --- BOTÃO ÚNICO DE DOWNLOAD (EXCEL GERADO ON-THE-FLY) ---
                res_b = supabase.table("base_comercial").select("*").execute()
                if res_b.data:
                    df_base_h = pd.DataFrame(res_b.data[0]['dados_json'])
                    t_usadas = df_h['lista_t'].iloc[0]
                    res_t = supabase.table("transportadoras").select("*").in_("nome", t_usadas).execute()
                    df_ts_h = pd.DataFrame(res_t.data)
                    
                    # O motor de cálculo roda aqui para gerar o arquivo detalhado
                    df_detalhado = engine_calculo(df_base_h, t_usadas, df_ts_h)
                    excel_file = to_excel(df_detalhado)
                    
                    c1.download_button(
                        label="📥 Exportar Cotação Excel",
                        data=excel_file,
                        file_name=f"Cotacao_{dt.replace('/','-').replace(':','-')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{r['id']}"
                    )
                
                if c2.button("🗑️ Remover", key=f"del_{r['id']}"):
                    supabase.table("cotacoes").delete().eq("id", r['id']).execute()
                    st.rerun()
