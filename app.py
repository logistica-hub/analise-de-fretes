import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime
import math

# 1. Configuração de Layout (Mantendo seu padrão)
st.set_page_config(page_title="Editora Ave-Maria | Fretes", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    [data-testid="stMetric"] { border: 1px solid #ddd; padding: 10px; border-radius: 8px; background-color: rgba(255,255,255,0.05); }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v19.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER, detalhes_json TEXT, estado_resumo TEXT)''')
    conn.commit()
    conn.close()

init_db()

if 'view_details' not in st.session_state: st.session_state.view_details = {}
if 'edit_id' not in st.session_state: st.session_state.edit_id = None

# --- SIDEBAR (Mantendo seu padrão) ---
with st.sidebar:
    if 'logo_data' not in st.session_state: st.session_state.logo_data = None
    if st.session_state.logo_data:
        st.image(st.session_state.logo_data, use_container_width=True)
        if st.button("✏️ Editar Logo"):
            st.session_state.logo_data = None
            st.rerun()
    else:
        up = st.file_uploader("🖼️ Subir Logo", type=["png", "jpg"])
        if up: 
            st.session_state.logo_data = up.read(); st.rerun()
    st.divider()
    menu = st.radio("MENU PRINCIPAL", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        todas_notas = []
        for _, row in df_h.iterrows():
            notas_lote = pd.read_json(io.StringIO(row['detalhes_json']))
            notas_lote['Transportadora_Ref'] = row['transportadora']
            if 'UF' not in notas_lote.columns:
                notas_lote['UF'] = notas_lote.iloc[:, 3]
            todas_notas.append(notas_lote)
        
        df_bi = pd.concat(todas_notas, ignore_index=True)
        st.markdown("### 🔍 Filtros Dinâmicos")
        f1, f2 = st.columns(2)
        filtro_t = f1.multiselect("Transportadora", df_bi['Transportadora_Ref'].unique())
        filtro_uf = f2.multiselect("Estado (UF)", sorted(df_bi['UF'].unique()))
        
        df_filtrado = df_bi.copy()
        if filtro_t: df_filtrado = df_filtrado[df_filtrado['Transportadora_Ref'].isin(filtro_t)]
        if filtro_uf: df_filtrado = df_filtrado[df_filtrado['UF'].isin(filtro_uf)]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_filtrado['VALOR_SISTEMA'].sum():,.2f}")
        c2.metric("Notas Processadas", f"{len(df_filtrado)}") 
        c3.metric("Ticket Médio", f"R$ {df_filtrado['VALOR_SISTEMA'].mean():,.2f}" if len(df_filtrado) > 0 else "R$ 0,00")

        if not df_filtrado.empty:
            st.subheader("📋 Resumo por Estado")
            pivot = df_filtrado.pivot_table(index="UF", columns="Transportadora_Ref", values="VALOR_SISTEMA", aggfunc="sum").fillna(0)
            st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Nenhuma cotação no banco de dados.")

# --- TRANSPORTADORAS ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    is_editing = st.session_state.edit_id is not None
    
    with st.expander("📝 Configurar Mapeamento", expanded=is_editing):
        edit_data = None
        # Adicionado mapeamento de colunas de cidades no dicionário padrão
        mapa_previo = {"faixas": [], "taxas": {}, "kg_extra": "Não mapear", "col_cid": "Não mapear", "col_sigla": "Não mapear"}
        if is_editing:
            conn = sqlite3.connect(DB_NAME)
            edit_data = pd.read_sql_query(f"SELECT * FROM transportadoras WHERE id={st.session_state.edit_id}", conn).iloc[0]
            conn.close()
            mapa_previo = json.loads(edit_data['mapeamento_json'])

        t_nome = st.text_input("Nome da Transportadora", value=edit_data['nome'] if is_editing else "").upper()
        col1, col2 = st.columns(2)
        f_tab = col1.file_uploader("Arquivo de Tabela (Excel)", type=["xlsx"])
        f_cid = col2.file_uploader("Arquivo de Cidades (Excel)", type=["xlsx"])
        
        df_t = None; df_c = None
        if f_tab: df_t = pd.read_excel(f_tab).fillna(0)
        elif is_editing: df_t = pd.read_json(io.StringIO(edit_data['tabela_json']))
        
        if f_cid: df_c = pd.read_excel(f_cid).fillna(0)
        elif is_editing: df_c = pd.read_json(io.StringIO(edit_data['cidades_json']))

        if df_t is not None and df_c is not None:
            cols_t = ["Não mapear"] + [str(c) for c in df_t.columns]
            cols_c = ["Não mapear"] + [str(c) for c in df_c.columns]
            
            st.markdown("---")
            st.subheader("📍 Mapeamento de Cidades e Siglas")
            c_geo1, c_geo2 = st.columns(2)
            sel_c = str(mapa_previo.get('col_cid', "Não mapear"))
            sel_s = str(mapa_previo.get('col_sigla', "Não mapear"))
            m_col_cid = c_geo1.selectbox("Coluna com nome da CIDADE", cols_c, index=cols_c.index(sel_c) if sel_c in cols_c else 0)
            m_col_sigla = c_geo2.selectbox("Coluna com a SIGLA/REGIÃO", cols_c, index=cols_c.index(sel_s) if sel_s in cols_c else 0)

            st.subheader("⚖️ Faixas de Peso")
            sel_kg = str(mapa_previo.get('kg_extra', "Não mapear"))
            col_kg_extra = st.selectbox("Coluna do Kg Adicional", cols_t, index=cols_t.index(sel_kg) if sel_kg in cols_t else 0)
            
            n_f_val = len(mapa_previo.get('faixas', [])) if is_editing else 6
            n_f = st.number_input("Quantidade de Faixas", 1, 50, n_f_val)
            faixas = []
            for i in range(int(n_f)):
                r = st.columns(3)
                f_ini = mapa_previo['faixas'][i] if is_editing and i < len(mapa_previo['faixas']) else {}
                faixas.append({
                    "min": r[0].number_input(f"De (kg)", value=float(f_ini.get('min', 0.0)), key=f"mi{i}"),
                    "max": r[1].number_input(f"Até (kg)", value=float(f_ini.get('max', 0.0)), key=f"ma{i}"),
                    "col": r[2].selectbox(f"Coluna na Tabela", cols_t, index=cols_t.index(str(f_ini.get('col', "Não mapear"))) if str(f_ini.get('col', "Não mapear")) in cols_t else 0, key=f"co{i}")
                })
            
            st.subheader("💰 Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}; t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                s_tx = str(mapa_previo.get('taxas', {}).get(tx, "Não mapear"))
                m_taxas[tx] = t_cols[idx % 3].selectbox(tx, cols_t, index=cols_t.index(s_tx) if s_tx in cols_t else 0, key=f"tx_{tx}")

            if st.button("💾 Salvar Transportadora"):
                mapa = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra, "col_cid": m_col_cid, "col_sigla": m_col_sigla}
                conn = sqlite3.connect(DB_NAME)
                if is_editing:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, cidades_json=?, mapeamento_json=? WHERE id=?",
                                 (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                                 (t_nome, df_t.to_json(), df_c.to_json(), json.dumps(mapa)))
                conn.commit(); conn.close(); st.session_state.edit_id = None; st.rerun()

    st.markdown("### 📋 Transportadoras Cadastradas")
    conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn); conn.close()
    for _, row in ts.iterrows():
        c1, c2, c3 = st.columns([7, 1.5, 1.5])
        c1.write(f"**{row['nome']}**")
        if c2.button("✏️ Editar", key=f"ed_{row['id']}"): st.session_state.edit_id = row['id']; st.rerun()
        if c3.button("🗑️ Excluir", key=f"dl_{row['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()

# --- COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Novo Cálculo de Frete")
    f_base = st.file_uploader("📥 Subir Planilha de Notas", type=["xlsx"])
    conn = sqlite3.connect(DB_NAME); ts = pd.read_sql_query("SELECT * FROM transportadoras", conn); conn.close()
    
    if not ts.empty:
        t_alvo = st.selectbox("Selecione a Transportadora", ts['nome'].tolist())
        if f_base and st.button("🚀 Calcular"):
            df_b = pd.read_excel(f_base).fillna(0); t_row = ts[ts['nome'] == t_alvo].iloc[0]
            df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
            df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
            mapa = json.loads(t_row['mapeamento_json'])
            
            # --- LÓGICA DE ALTA PERFORMANCE (Vetorização) ---
            df_b['CIDADE_NF'] = df_b.iloc[:, 2].astype(str).str.upper().str.strip()
            
            # Usando as colunas mapeadas pelo usuário para evitar o erro de 'CIDADE'
            col_cid_apoio = mapa.get('col_cid', df_cid_ref.columns[0])
            col_sigla_apoio = mapa.get('col_sigla', df_cid_ref.columns[2])
            
            df_cid_ref['BUSCA_CIDADE'] = df_cid_ref[col_cid_apoio].astype(str).str.upper().str.strip()
            df_proc = pd.merge(df_b, df_cid_ref[['BUSCA_CIDADE', col_sigla_apoio]], left_on='CIDADE_NF', right_on='BUSCA_CIDADE', how='left')
            
            res_final = []
            for _, nf in df_proc.iterrows():
                try:
                    peso_nf = float(nf.iloc[6]); valor_nf = float(nf.iloc[7]); sigla = str(nf[col_sigla_apoio])
                    # Localiza linha na tabela de preços pela sigla
                    precos = df_tab[df_tab.iloc[:,2].astype(str).str.upper().str.strip() == sigla.upper().strip()].iloc[0]
                    
                    f_peso = 0.0; u_max = 0; u_col = ""; d = False
                    for f in mapa['faixas']:
                        u_max, u_col = f['max'], f['col']
                        if peso_nf <= f['max'] and f['col'] != "Não mapear":
                            f_peso = float(precos[f['col']]); d = True; break
                    if not d and mapa.get('kg_extra') != "Não mapear":
                        f_peso = float(precos[u_col]) + ((peso_nf - u_max) * float(precos[mapa['kg_extra']]))
                    
                    def gv(n): return float(precos[mapa['taxas'][n]]) if n in mapa['taxas'] and mapa['taxas'][n] != "Não mapear" else 0.0
                    v_adv = max(valor_nf * gv("Ad Valorem %"), gv("Ad Valorem Min"))
                    v_gris = max(valor_nf * gv("Gris %"), gv("Gris Min"))
                    v_emex = max(valor_nf * gv("Emex %"), gv("Emex Min"))
                    v_pedagio = math.ceil(peso_nf / 100) * gv("Pedagio")
                    
                    total_nf = f_peso + v_adv + v_gris + v_emex + v_pedagio + gv("TAS") + gv("CTRC") + gv("TRT") + gv("TDA") + gv("SEC-CAT")
                    nf['VALOR_SISTEMA'] = total_nf
                    nf['MEMORIA_CALCULO'] = f"Frete Peso: R$ {f_peso:.2f} | AdV: R$ {v_adv:.2f} | Gris: R$ {v_gris:.2f} | Ped: R$ {v_pedagio:.2f}"
                except:
                    nf['VALOR_SISTEMA'] = 0.0; nf['MEMORIA_CALCULO'] = "Erro no mapeamento ou cidade não encontrada."
                res_final.append(nf.to_dict())

            df_res = pd.DataFrame(res_final)
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json) VALUES (?,?,?,?,?)",
                         (datetime.now().strftime("%d/%m %H:%M"), t_alvo, df_res['VALOR_SISTEMA'].sum(), len(df_res), df_res.to_json(orient='records')))
            conn.commit(); conn.close()
            
            st.success(f"✅ Processamento de {len(df_res)} Notas concluído.")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_res.to_excel(writer, index=False)
            st.download_button("📥 Baixar Resultados", output.getvalue(), f"Frete_{t_alvo}.xlsx")
            st.dataframe(df_res, use_container_width=True)

    # --- HISTÓRICO ---
    st.markdown("### 📄 Histórico")
    conn = sqlite3.connect(DB_NAME); df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn); conn.close()
    for _, row in df_h.iterrows():
        with st.expander(f"🔽 {row['data_hora']} - {row['transportadora']} | R$ {row['total']:,.2f}"):
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            if st.button("🗑️ Excluir", key=f"del_{row['id']}"):
                conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
            st.dataframe(df_det, use_container_width=True)
