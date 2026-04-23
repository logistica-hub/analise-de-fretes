import streamlit as st
import pandas as pd
from supabase import create_client, Client
import json
import io
import os
from datetime import datetime
import unicodedata
import numpy as np

# --- CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Ave-Maria | Fretes Profissional", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- UTILITÁRIOS ---
def normalizar(txt):
    if not txt or pd.isna(txt): return ""
    txt = str(txt).upper().strip()
    return "".join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def formata_br(valor):
    try:
        if pd.isna(valor) or valor == 0: return "0,00"
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

# --- SIDEBAR (LOGO E NAVEGAÇÃO) ---
with st.sidebar:
    # 1. GESTÃO DO LOGO (RESTAURADO)
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
    menu = st.radio("MENU", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])
    st.divider()
    st.caption("Conectado ao Supabase Cloud ✅")

# --- DASHBOARD (CONSOLIDADO E COM FILTROS) ---
if menu == "📊 Dashboard":
    st.title("📊 Indicadores de Performance")
    
    res = supabase.table("cotacoes").select("*").execute()
    if res.data:
        all_data = []
        for r in res.data:
            df_temp = pd.DataFrame(r['detalhes_json'])
            if not df_temp.empty:
                all_data.append(df_temp)
        
        if all_data:
            df_total = pd.concat(all_data, ignore_index=True)

            # 5. FILTROS (CORRIGIDO PARA EVITAR TYPEERROR)
            st.subheader("🎯 Filtros")
            f1, f2 = st.columns(2)
            
            # Limpeza de valores nulos para o sorted
            lista_ufs = sorted([str(x) for x in df_total['UF'].dropna().unique() if x != ""])
            lista_transp = sorted([str(x) for x in df_total['T_NOME'].dropna().unique() if x != ""])

            filtro_uf = f1.multiselect("Filtrar por UF", options=lista_ufs)
            filtro_tr = f2.multiselect("Filtrar por Transportadora", options=lista_transp)

            if filtro_uf: df_total = df_total[df_total['UF'].isin(filtro_uf)]
            if filtro_tr: df_total = df_total[df_total['T_NOME'].isin(filtro_tr)]

            # 4. CONSOLIDADO UF E VALOR
            col_met1, col_met2 = st.columns(2)
            col_met1.metric("Total Geral Cotado", f"R$ {formata_br(df_total['VALOR_SISTEMA'].sum())}")
            col_met2.metric("Total de Notas", len(df_total))

            st.write("### 💰 Consolidação por UF e Transportadora")
            consolidado = df_total.groupby(['UF', 'T_NOME'])['VALOR_SISTEMA'].sum().reset_index()
            # Ordenar por valor maior primeiro
            consolidado = consolidado.sort_values('VALOR_SISTEMA', ascending=False)
            consolidado['VALOR_SISTEMA'] = consolidado['VALOR_SISTEMA'].apply(lambda x: f"R$ {formata_br(x)}")
            st.dataframe(consolidado, use_container_width=True)
        else:
            st.warning("Dados inconsistentes no histórico.")
    else:
        st.info("Nenhum dado processado ainda. Vá em 'Comparativo' para calcular seu primeiro frete.")

# --- TRANSPORTADORAS (MAPEAMENTO COMPLETO) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    
    res_t = supabase.table("transportadoras").select("*").execute()
    df_list = pd.DataFrame(res_t.data)

    with st.expander("📝 Configuração de Mapeamento", expanded=st.session_state.get('edit_id') is not None):
        e_id = st.session_state.get('edit_id')
        e_row = df_list[df_list['id'] == e_id].iloc[0] if e_id is not None else None
        
        nome_t = st.text_input("Nome da Transportadora", value=e_row['nome'] if e_row is not None else "").upper()
        c1, c2 = st.columns(2)
        f_tab = c1.file_uploader("Subir Tabela de Preços")
        f_abr = c2.file_uploader("Subir Planilha de Abrangência")

        df_t = pd.read_excel(f_tab).fillna(0) if f_tab else (pd.DataFrame(e_row['tabela_json']) if e_row is not None else None)
        df_a = pd.read_excel(f_abr).fillna(0) if f_abr else (pd.DataFrame(e_row['cidades_json']) if e_row is not None else None)

        if df_t is not None and df_a is not None:
            mapa = e_row['mapeamento_json'] if e_row is not None else {}
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_a = ["Não mapear"] + [str(c) for c in df_a.columns]

            st.subheader("🔗 2. Mapeamento de Colunas (Obrigatório)")
            l1, l2 = st.columns(2)
            m_ap_cid = l1.selectbox("Abrangência: Coluna Cidade", cols_a, index=cols_a.index(mapa.get('ap_cidade')) if mapa.get('ap_cidade') in cols_a else 0)
            m_ap_sig = l1.selectbox("Abrangência: Coluna Sigla (Chave)", cols_a, index=cols_a.index(mapa.get('ap_sigla')) if mapa.get('ap_sigla') in cols_a else 0)
            m_tb_sig = l2.selectbox("Tabela: Coluna Sigla (Match)", cols_t, index=cols_t.index(mapa.get('tab_sigla')) if mapa.get('tab_sigla') in cols_t else 0)
            m_tb_uf = l2.selectbox("Tabela: Coluna UF", cols_t, index=cols_t.index(mapa.get('tab_uf')) if mapa.get('tab_uf') in cols_t else 0)

            st.subheader("⚖️ 3. Regras de Peso e Faixas")
            col_kg_ex = st.selectbox("Coluna Preço Kg Adicional", cols_t, index=cols_t.index(mapa.get('kg_extra')) if mapa.get('kg_extra') in cols_t else 0)
            n_faixas = st.number_input("Quantidade de Faixas de Peso", 1, 50, len(mapa.get('faixas', [])) or 6)
            faixas = []
            for i in range(int(n_faixas)):
                r = st.columns(3)
                f_ini = mapa.get('faixas', [])[i] if i < len(mapa.get('faixas', [])) else {}
                faixas.append({
                    "min": r[0].number_input("De (kg)", value=float(f_ini.get('min', 0.0)), key=f"min{i}"),
                    "max": r[1].number_input("Até (kg)", value=float(f_ini.get('max', 0.0)), key=f"max{i}"),
                    "col": r[2].selectbox("Coluna na Tabela", cols_t, index=cols_t.index(f_ini.get('col')) if f_ini.get('col') in cols_t else 0, key=f"col{i}")
                })

            st.subheader("💰 4. Mapeamento de Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "SEC-CAT", "Suframa", "EMEX", "TRT", "TDA"]
            m_taxas = {}; tx_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                v_tx = mapa.get('taxas', {}).get(tx, "Não mapear")
                m_taxas[tx] = tx_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(v_tx) if v_tx in cols_t else 0)

            if st.button("💾 Salvar Transportadora"):
                mapa_final = {"ap_cidade": m_ap_cid, "ap_sigla": m_ap_sig, "tab_sigla": m_tb_sig, "tab_uf": m_tb_uf, "faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_ex}
                payload = {"nome": nome_t, "tabela_json": df_t.to_dict(orient='records'), "cidades_json": df_a.to_dict(orient='records'), "mapeamento_json": mapa_final}
                if e_id: supabase.table("transportadoras").update(payload).eq("id", e_id).execute()
                else: supabase.table("transportadoras").insert(payload).execute()
                st.session_state.edit_id = None; st.success("Transportadora salva!"); st.rerun()

    # LISTAGEM PARA GESTÃO
    if not df_list.empty:
        for _, r in df_list.iterrows():
            col_list = st.columns([7, 1, 1])
            col_list[0].write(f"**{r['nome']}**")
            if col_list[1].button("✏️", key=f"ed{r['id']}"): st.session_state.edit_id = r['id']; st.rerun()
            if col_list[2].button("🗑️", key=f"dl{r['id']}"): supabase.table("transportadoras").delete().eq("id", r['id']).execute(); st.rerun()

# --- COMPARATIVO (HISTÓRICO E EXPANSÃO) ---
elif menu == "💰 Comparativo":
    st.title("💰 Cálculo de Frete Massivo")
    
    f_notas = st.file_uploader("📥 Passo 1: Subir Planilha de Notas (Excel)", type=["xlsx"])
    res_t = supabase.table("transportadoras").select("*").execute()
    df_ts = pd.DataFrame(res_t.data)

    if f_notas and not df_ts.empty:
        selecionadas = st.multiselect("Passo 2: Selecionar Transportadoras para comparar", df_ts['nome'].tolist())
        if selecionadas and st.button("🚀 Passo 3: Calcular Fretes"):
            with st.spinner("Processando..."):
                df_base = pd.read_excel(f_notas).fillna(0)
                resultados_lote = []
                
                for t_nome in selecionadas:
                    t_row = df_ts[df_ts['nome'] == t_nome].iloc[0]
                    m = t_row['mapeamento_json']
                    df_tab = pd.DataFrame(t_row['tabela_json'])
                    df_abr = pd.DataFrame(t_row['cidades_json'])
                    
                    df_calc = df_base.copy()
                    df_calc['KEY_CIDADE'] = df_calc.iloc[:, 2].astype(str).apply(normalizar) # Assume coluna 3 como Cidade
                    df_abr['KEY_REF'] = df_abr[m['ap_cidade']].astype(str).apply(normalizar)
                    df_tab['KEY_TAB'] = df_tab[m['tab_sigla']].astype(str).apply(normalizar)
                    
                    df_m1 = pd.merge(df_calc, df_abr[[m['ap_sigla'], 'KEY_REF']], left_on='KEY_CIDADE', right_on='KEY_REF', how='left')
                    df_m1['KEY_MATCH'] = df_m1[m['ap_sigla']].astype(str).apply(normalizar)
                    df_final = pd.merge(df_m1, df_tab, left_on='KEY_MATCH', right_on='KEY_TAB', how='left')
                    
                    # Variáveis Numéricas
                    peso = pd.to_numeric(df_final.iloc[:, 6], errors='coerce').fillna(0) # Coluna 7: Peso
                    valor_nf = pd.to_numeric(df_final.iloc[:, 7], errors='coerce').fillna(0) # Coluna 8: Valor
                    
                    # Cálculo Frete Peso
                    df_final['F_PESO'] = 0.0
                    for f in m['faixas']:
                        if f['col'] in df_final.columns:
                            mask = (peso <= f['max']) & (df_final['F_PESO'] == 0.0)
                            df_final.loc[mask, 'F_PESO'] = pd.to_numeric(df_final.loc[mask, f['col']], errors='coerce').fillna(0)
                    
                    # Regra Kg Extra
                    if m.get('kg_extra') in df_final.columns:
                        u_max = m['faixas'][-1]['max']
                        u_col = m['faixas'][-1]['col']
                        mask_e = (peso > u_max)
                        v_base = pd.to_numeric(df_final.loc[mask_e, u_col], errors='coerce').fillna(0)
                        v_adic = pd.to_numeric(df_final.loc[mask_e, m['kg_extra']], errors='coerce').fillna(0)
                        df_final.loc[mask_e, 'F_PESO'] = v_base + ((peso[mask_e] - u_max) * v_adic)

                    def gv(name):
                        col = m['taxas'].get(name, "Não mapear")
                        return pd.to_numeric(df_final[col], errors='coerce').fillna(0) if col in df_final.columns else 0.0

                    df_final['ADVAL'] = np.maximum(valor_nf * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                    df_final['GRIS'] = np.maximum(valor_nf * gv("Gris %"), gv("Gris Min"))
                    df_final['PEDAGIO'] = np.ceil(peso / 100) * gv("Pedagio")
                    df_final['OUTRAS'] = gv("TAS") + gv("CTRC") + gv("SEC-CAT") + gv("Suframa") + gv("EMEX") + gv("TRT") + gv("TDA")
                    
                    df_final['VALOR_SISTEMA'] = df_final['F_PESO'] + df_final['ADVAL'] + df_final['GRIS'] + df_final['PEDAGIO'] + df_final['OUTRAS']
                    df_final['T_NOME'] = t_nome
                    df_final['UF'] = df_final[m['tab_uf']] if m['tab_uf'] in df_final.columns else "ND"
                    
                    resultados_lote.append(df_final)

                df_full = pd.concat(resultados_lote)
                payload = {"data_hora": datetime.now().strftime("%d/%m/%Y %H:%M"), "total": float(df_full['VALOR_SISTEMA'].sum()), "qtd": len(df_base), "detalhes_json": df_full.to_dict(orient='records')}
                supabase.table("cotacoes").insert(payload).execute()
                st.success("Cálculo finalizado!"); st.rerun()

    # 3. LISTAGEM DE COMPARATIVOS (HISTÓRICO)
    st.divider()
    st.subheader("🕒 Histórico de Cálculos")
    res_h = supabase.table("cotacoes").select("*").order("id", desc=True).execute()
    
    for r in res_h.data:
        with st.expander(f"📦 Lote {r['data_hora']} | {r['qtd']} notas | R$ {formata_br(r['total'])}"):
            df_h = pd.DataFrame(r['detalhes_json'])
            transp_no_lote = df_h['T_NOME'].unique()
            
            # REGRA 3: Expandir com base na quantidade de transportadoras
            if len(transp_no_lote) == 1:
                st.info(f"Detalhamento de Taxas: {transp_no_lote[0]}")
                cols_det = ['UF', 'VALOR_SISTEMA', 'F_PESO', 'ADVAL', 'GRIS', 'PEDAGIO', 'OUTRAS']
                st.dataframe(df_h[cols_det], use_container_width=True)
            else:
                st.info("Comparativo Consolidado entre Transportadoras")
                resumo = df_h.groupby('T_NOME')['VALOR_SISTEMA'].sum().reset_index()
                resumo['VALOR_SISTEMA'] = resumo['VALOR_SISTEMA'].apply(lambda x: f"R$ {formata_br(x)}")
                st.table(resumo)
                if st.button("Ver Detalhes das Notas", key=f"btn_v_{r['id']}"):
                    st.dataframe(df_h)
            
            if st.button("🗑️ Excluir este Histórico", key=f"del_h_{r['id']}"):
                supabase.table("cotacoes").delete().eq("id", r['id']).execute()
                st.rerun()
