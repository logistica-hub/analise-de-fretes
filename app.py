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

# CSS Original do Usuário (Versão 19.0)
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
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .metric-label {
        font-size: 13px;
        color: #64748b;
        margin-bottom: 8px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 22px;
        color: #1e293b;
        font-weight: 800;
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

def to_excel(df_completo):
    output = BytesIO()
    cols_total = [c for c in df_completo.columns if c.startswith("TOTAL_")]
    transportadoras = [c.replace("TOTAL_", "") for c in cols_total]
    
    # Adicionado SUFRAMA, FLUVIAL e REDESPACHO_F ao filtro de prefixos para organização por abas
    prefixos = ["PESO_BASE_", "KG_ADIC_", "ADVAL_", "GRIS_", "EMEX_", "PEDAGIO_", "TAS_", "CTRC_", "SUFRAMA_", "FLUVIAL_", "REDESPACHO_F_", "OUTROS_", "TOTAL_"]
    
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
    st.title("Ave Maria - Analise de Fretes")
    st.info("Versão 19.0")
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Alterar Logo"):
            st.session_state.logo_data = None
            st.rerun()
    else:
        up_logo = st.file_uploader("🖼️ Logo da Empresa", type=["png", "jpg", "jpeg"])
        if up_logo:
            st.session_state.logo_data = up_logo.read()
            st.rerun()
    st.divider()
    menu = st.radio("Navegação", ["📊 Dashboard", "📂 Base Comercial", "🚛 Cadastro de Transportadora", "💰 Comparativo", "📜 Histórico"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Frete")
    # Busca dados completos apenas para o Dashboard
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        all_dfs = [pd.DataFrame(r['detalhes_json']) for r in res.data if r['detalhes_json']]
        if all_dfs:
            df_total = pd.concat(all_dfs, ignore_index=True)
            cols_f = [c for c in df_total.columns if c.startswith("TOTAL_")]
            nomes_t = [c.replace("TOTAL_", "") for c in cols_f]
            
            with st.container():
                f1, f2, f3 = st.columns([1.5, 2.5, 1.5])
                sel_tr = f1.multiselect("🚛 Transportadoras", nomes_t, default=nomes_t)
                col_uf = next((c for c in df_total.columns if c.upper() == 'UF'), None)
                lista_ufs = sorted(df_total[col_uf].unique()) if col_uf else []
                sel_uf = f2.multiselect("📍 Estados (UF)", lista_ufs, default=lista_ufs)
                col_data = next((c for c in df_total.columns if c.upper() in ['MÊS', 'MES', 'DATA']), None)
                lista_datas = sorted(df_total[col_data].unique()) if col_data else []
                sel_data = f3.multiselect("📅 Período", lista_datas, default=lista_datas)
            
            df_filt = df_total.copy()
            if col_uf: df_filt = df_filt[df_filt[col_uf].isin(sel_uf)]
            if col_data: df_filt = df_filt[df_filt[col_data].isin(sel_data)]
            cols_sel = [f"TOTAL_{t}" for t in sel_tr]
            
            if not df_filt.empty and cols_sel:
                col_val_nf = next((c for c in df_filt.columns if 'VALOR' in c.upper() and 'FRETE' not in c.upper()), None)
                val_total_notas = df_filt[col_val_nf].sum() if col_val_nf else 0
                col_peso = next((c for c in df_filt.columns if 'PESO' in c.upper() and 'BASE' not in c.upper()), None)
                peso_total = df_filt[col_peso].sum() if col_peso else 0
                val_total_frete = df_filt[cols_sel].sum().sum()
                
                st.markdown("<br>", unsafe_allow_html=True)
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.markdown(f'<div class="metric-card"><div class="metric-label">NOTAS PROCESSADAS</div><div class="metric-value">{len(df_filt)}</div></div>', unsafe_allow_html=True)
                with m2: st.markdown(f'<div class="metric-card"><div class="metric-label">VALOR TOTAL NOTAS</div><div class="metric-value">{format_brl(val_total_notas)}</div></div>', unsafe_allow_html=True)
                with m3: st.markdown(f'<div class="metric-card"><div class="metric-label">PESO TOTAL</div><div class="metric-value">{format_kg(peso_total)}</div></div>', unsafe_allow_html=True)
                with m4: st.markdown(f'<div class="metric-card"><div class="metric-label">INVESTIMENTO EM FRETE</div><div class="metric-value">{format_brl(val_total_frete)}</div></div>', unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                st.subheader("💰 Melhor Custo por Estado")
                if col_uf:
                    df_uf = df_filt.groupby(col_uf)[cols_sel].sum()
                    df_uf.columns = [c.replace("TOTAL_", "") for c in df_uf.columns]
                    def highlight_min_no_zero(s):
                        s_validos = s[s > 0]
                        is_min = s == s_validos.min() if not s_validos.empty else [False]*len(s)
                        return ['background-color: #ecfdf5; color: #065f46; font-weight: bold; border: 1px solid #10b981' if v else 'color: #475569' for v in is_min]
                    st.dataframe(df_uf.style.apply(highlight_min_no_zero, axis=1).format(format_brl), use_container_width=True, height=500)
    else: st.info("Sem histórico de cotações para exibir.")

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
                m_ap_sig = st.selectbox("Coluna Sigla (na Relação)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            st.divider(); st.markdown("### ⚖️ Mapeamento de Faixas de Peso")
            n_f = st.number_input("Qtd Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3); f_i = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({"min": r[0].number_input("De kg", value=float(f_i.get('min', 0.0)), key=f"mi{i}"), "max": r[1].number_input("Até kg", value=float(f_i.get('max', 0.0)), key=f"ma{i}"), "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_i.get('col')) if f_i.get('col') in cols_t else 0, key=f"co{i}")})
            st.divider(); st.markdown("### 💰 Mapeamento de Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "Suframa", "Fluvial", "Redespacho Fluvial"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0, key=f"tx_{idx}")
            if st.button("💾 Salvar Transportadora"):
                payload = {"nome": nome_t, "tabela_json": df_t.to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.session_state.form_reset_key += 1; st.rerun()
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
        st.info(f"Utilizando Base Comercial salva: {len(df_base)} notas.")
        selecionadas = st.multiselect("Selecione as Transportadoras", df_ts['nome'].tolist())
        
        if selecionadas and st.button("🚀 Calcular"):
            progresso_bar = st.progress(0)
            status_text = st.empty()
            total_tr = len(selecionadas)
            df_final = df_base.copy()
            
            col_cid_nome = next((c for c in df_base.columns if 'CIDADE' in c.upper()), df_base.columns[2])
            col_peso_nome = next((c for c in df_base.columns if 'PESO' in c.upper() and 'BASE' not in c.upper()), df_base.columns[6])
            col_valor_nome = next((c for c in df_base.columns if 'VALOR' in c.upper() and 'FRETE' not in c.upper()), df_base.columns[7])
            
            cid_notas = df_base[col_cid_nome].astype(str).apply(super_limpeza).values
            pesos_notas = pd.to_numeric(df_base[col_peso_nome], errors='coerce').fillna(0).values
            valores_notas = pd.to_numeric(df_base[col_valor_nome], errors='coerce').fillna(0).values

            for idx, t_nome in enumerate(selecionadas):
                percentual = (idx) / total_tr
                progresso_bar.progress(percentual)
                status_text.text(f"Calculando frete: {t_nome} ({idx + 1}/{total_tr})")

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
                
                # CORREÇÃO: Taxas detalhadas com colunas próprias
                suf = valores_notas * get_v(m['taxas'].get("Suframa"))
                fluv = valores_notas * get_v(m['taxas'].get("Fluvial"))
                red_f = get_v(m['taxas'].get("Redespacho Fluvial"))

                df_final[f'PESO_BASE_{t_nome}'] = f_peso - v_kg_adic
                df_final[f'KG_ADIC_{t_nome}'] = v_kg_adic
                df_final[f'ADVAL_{t_nome}'] = adv
                df_final[f'GRIS_{t_nome}'] = grs
                df_final[f'EMEX_{t_nome}'] = emx
                df_final[f'PEDAGIO_{t_nome}'] = ped
                df_final[f'TAS_{t_nome}'] = get_v(m['taxas'].get("TAS"))
                df_final[f'CTRC_{t_nome}'] = get_v(m['taxas'].get("CTRC"))
                
                # Detalhamento solicitado
                df_final[f'SUFRAMA_{t_nome}'] = suf
                df_final[f'FLUVIAL_{t_nome}'] = fluv
                df_final[f'REDESPACHO_F_{t_nome}'] = red_f
                df_final[f'OUTROS_{t_nome}'] = 0.0 # Zerado pois agora estão detalhados acima
                
                df_final[f'TOTAL_{t_nome}'] = f_peso + adv + grs + emx + ped + get_v(m['taxas'].get("TAS")) + get_v(m['taxas'].get("CTRC")) + suf + fluv + red_f

            progresso_bar.progress(1.0)
            
            try:
                data_sao_paulo = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")
                dados_completos = df_final.fillna(0).to_dict(orient='records')
                tamanho_lote = 2000
                total_lotes = (len(dados_completos) // tamanho_lote) + 1
                
                for i in range(0, len(dados_completos), tamanho_lote):
                    lote = dados_completos[i:i + tamanho_lote]
                    lote_num = (i // tamanho_lote) + 1
                    status_text.text(f"💾 Salvando lote {lote_num} de {total_lotes}...")
                    supabase.table("cotacoes").insert({"data_hora": data_sao_paulo, "qtd": len(lote), "detalhes_json": lote}).execute()
                
                st.success(f"Cotação salva com sucesso!")
                st.rerun()
            except Exception as e: 
                st.error(f"Erro ao salvar histórico: {e}")
    else: st.warning("Cadastre a Base Comercial e as Transportadoras.")

# --- HISTÓRICO (OTIMIZADO COM LAZY LOADING) ---
elif menu == "📜 Histórico":
    st.title("📜 Histórico de Cotações")
    # OTIMIZAÇÃO: Busca apenas metadados (id, data, qtd) para carregar a tela instantaneamente
    res_h = supabase.table("cotacoes").select("id, data_hora, qtd").order("id", desc=True).execute()
    
    if res_h.data:
        df_meta = pd.DataFrame(res_h.data)
        # Agrupa por data_hora para mostrar blocos de relatórios
        for data_ref, g in df_meta.groupby("data_hora", sort=False):
            with st.expander(f"📦 {data_ref} | {g['qtd'].sum()} Notas"):
                # O detalhe (JSON pesado) só é buscado se o usuário clicar no botão de baixar
                c_btn1, c_btn2 = st.columns(2)
                
                if c_btn1.button(f"🔍 Preparar Download", key=f"prep_{g['id'].iloc[0]}"):
                    with st.spinner("Baixando dados detalhados..."):
                        # Busca os detalhes_json apenas deste registro específico
                        ids_lote = g['id'].tolist()
                        res_detalhe = supabase.table("cotacoes").select("detalhes_json").in_("id", ids_lote).execute()
                        
                        det_full = []
                        for item in res_detalhe.data:
                            d = item['detalhes_json']
                            if isinstance(d, list): det_full.extend(d)
                            elif isinstance(d, dict): det_full.append(d)
                        
                        df_det = pd.DataFrame(det_full)
                        excel_data = to_excel(df_det)
                        
                        st.download_button(
                            "📥 Clique aqui para Baixar Excel",
                            data=excel_data,
                            file_name=f"Cotacao_{data_ref.replace('/','-')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_ready_{g['id'].iloc[0]}"
                        )
                
                if c_btn2.button("🗑️ Remover Registro", key=f"del_{g['id'].iloc[0]}"):
                    for rid in g['id']:
                        supabase.table("cotacoes").delete().eq("id", rid).execute()
                    st.rerun()
    else:
        st.info("Nenhuma cotação salva no histórico.")
