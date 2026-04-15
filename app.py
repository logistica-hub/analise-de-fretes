import streamlit as st
import pandas as pd
import sqlite3
import json
import io
from datetime import datetime

# 1. Configuração de Layout e Visual BI
st.set_page_config(page_title="Comparativo de Tabelas", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .block-container { padding-top: 0.5rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%; }
    [data-testid="stSidebar"] { background-color: #F8F9FA !important; border-right: 1px solid #E0E0E0; }
    [data-testid="stSidebar"] * { color: #000000 !important; font-weight: 600; }
    .stMetric { border: 1px solid #F0F0F0; padding: 10px; border-radius: 8px; background: #FFF; }
    /* Estilo para as linhas de mapeamento ficarem separadas */
    .mapping-row { border-bottom: 1px solid #eee; padding: 10px 0; }
    hr { margin: 10px 0; border-top: 1px solid #DDD; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'comparativo_v14.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transportadoras 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, tabela_json TEXT, 
                  cidades_json TEXT, mapeamento_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cotacoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, transportadora TEXT, 
                  total REAL, qtd INTEGER, detalhes_json TEXT, estado_resumo TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- SIDEBAR ---
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
            st.session_state.logo_data = up.read()
            st.rerun()
    
    st.divider()
    menu = st.radio("NAVEGAÇÃO", ["📊 Dashboard", "🚛 Transportadoras", "💰 Comparativo"])

# --- TELA: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Painel de Indicadores")
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes", conn)
    conn.close()

    if not df_h.empty:
        resumos = []
        for r in df_h['estado_resumo']: resumos.extend(json.loads(r))
        df_full = pd.DataFrame(resumos)

        f1, f2 = st.columns(2)
        with f1: t_sel = st.multiselect("Transportadora", df_full['Transportadora'].unique())
        with f2: uf_sel = st.multiselect("Estado (UF)", sorted(df_full['UF'].unique()))

        if t_sel: df_full = df_full[df_full['Transportadora'].isin(t_sel)]
        if uf_sel: df_full = df_full[df_full['UF'].isin(uf_sel)]

        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cotado", f"R$ {df_full['Valor'].sum():,.2f}")
        c2.metric("Notas Processadas", int(df_h['qtd'].sum()))
        c3.metric("Ticket Médio", f"R$ {df_full['Valor'].mean():,.2f}" if not df_full.empty else "0")

        st.subheader("📋 Consolidado por UF")
        pivot = df_full.pivot_table(index="UF", columns="Transportadora", values="Valor", aggfunc="sum").fillna(0)
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Nenhuma cotação realizada ainda.")

# --- TELA: TRANSPORTADORAS (MAPEAMENTO EM LISTA) ---
elif menu == "🚛 Transportadoras":
    st.title("🚛 Gestão de Transportadoras")
    
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    edit_nome = ""
    if st.session_state.edit_id:
        conn = sqlite3.connect(DB_NAME)
        res = conn.execute("SELECT nome FROM transportadoras WHERE id=?", (st.session_state.edit_id,)).fetchone()
        conn.close()
        if res: edit_nome = res[0]

    with st.expander("📝 Configurar Tabela, Cidades e Taxas", expanded=(st.session_state.edit_id is not None)):
        t_nome = st.text_input("Nome da Transportadora", value=edit_nome).upper()
        u1, u2 = st.columns(2)
        with u1: f_tab = st.file_uploader("Tabela de Frete (Excel)", type=["xlsx"])
        with u2: f_cid = st.file_uploader("Cidades/Siglas (Excel)", type=["xlsx"])
        
        if f_tab:
            df_t = pd.read_excel(f_tab).fillna(0)
            cols_tabela = ["Não mapear"] + list(df_t.columns)
            
            # 1. MAPEAMENTO DE PESO EM LISTA
            st.markdown("### ⚖️ Mapeamento de Faixas de Peso")
            st.info("Defina as faixas de peso e selecione a coluna correspondente na sua planilha.")
            
            n_f = st.number_input("Quantidade de Faixas", 1, 50, 6)
            faixas = []
            
            # Cabeçalho da Lista
            h1, h2, h3 = st.columns([1, 1, 2])
            h1.caption("Peso Min (kg)")
            h2.caption("Peso Max (kg)")
            h3.caption("Coluna na Planilha")

            for i in range(int(n_f)):
                with st.container():
                    r = st.columns([1, 1, 2])
                    mi = r[0].number_input(f"Min", key=f"mi{i}", label_visibility="collapsed")
                    ma = r[1].number_input(f"Max", key=f"ma{i}", label_visibility="collapsed")
                    co = r[2].selectbox(f"Col", cols_tabela, key=f"co{i}", label_visibility="collapsed")
                    faixas.append({"min": mi, "max": ma, "col": co})
            
            # 2. KG ADICIONAL (NOVO)
            st.markdown("---")
            st.markdown("### ➕ Kg Adicional")
            col_kg_extra = st.selectbox("Selecione a coluna de valor por Kg Adicional (Excedente)", cols_tabela)
            
            # 3. MAPEAMENTO DE TAXAS
            st.markdown("---")
            st.markdown("### 💰 Taxas Adicionais")
            taxas_nomes = ["Ad Valorem %", "Ad Valorem Min", "TAS", "CTRC", "Pedagio", "Gris %", "Gris Min", "Emex %", "Emex Min", "TRT", "TDA", "SEC-CAT"]
            m_taxas = {}
            t_cols = st.columns(3)
            for idx, tx in enumerate(taxas_nomes):
                with t_cols[idx % 3]:
                    m_taxas[tx] = st.selectbox(tx, cols_tabela, key=f"tx_{tx}")

            if st.button("💾 Salvar Transportadora"):
                mapa_final = {"faixas": faixas, "taxas": m_taxas, "kg_extra": col_kg_extra}
                conn = sqlite3.connect(DB_NAME)
                if st.session_state.edit_id:
                    conn.execute("UPDATE transportadoras SET nome=?, tabela_json=?, mapeamento_json=? WHERE id=?",
                                 (t_nome, df_t.to_json(), json.dumps(mapa_final), st.session_state.edit_id))
                else:
                    conn.execute("INSERT INTO transportadoras (nome, tabela_json, cidades_json, mapeamento_json) VALUES (?,?,?,?)",
                                 (t_nome, df_t.to_json(), pd.read_excel(f_cid).to_json(), json.dumps(mapa_final)))
                conn.commit(); conn.close()
                st.session_state.edit_id = None
                st.success("Configuração salva!"); st.rerun()

    st.divider()
    conn = sqlite3.connect(DB_NAME)
    df_l = pd.read_sql_query("SELECT id, nome FROM transportadoras", conn)
    conn.close()
    for _, r in df_l.iterrows():
        c = st.columns([6, 1, 1])
        c[0].write(f"🏢 **{r['nome']}**")
        if c[1].button("✏️", key=f"ed_{r['id']}"):
            st.session_state.edit_id = r['id']; st.rerun()
        if c[2].button("🗑️", key=f"dl_{r['id']}"):
            conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM transportadoras WHERE id=?", (r['id'],)); conn.commit(); conn.close(); st.rerun()

# --- TELA: COMPARATIVO ---
elif menu == "💰 Comparativo":
    st.title("💰 Comparativo de Fretes")
    f_base = st.file_uploader("📥 Subir Planilha Base (Notas)", type=["xlsx"])
    
    if f_base:
        df_b = pd.read_excel(f_base).fillna(0)
        st.markdown("### 🔍 Configuração das Colunas da Base")
        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1: b_cid = st.selectbox("Coluna Cidade", df_b.columns, index=2)
        with bc2: b_uf = st.selectbox("Coluna UF", df_b.columns, index=3)
        with bc3: b_peso = st.selectbox("Coluna Peso", df_b.columns, index=6)
        with bc4: b_val = st.selectbox("Coluna Valor NF", df_b.columns, index=7)

        conn = sqlite3.connect(DB_NAME)
        ts = pd.read_sql_query("SELECT * FROM transportadoras", conn)
        conn.close()

        if not ts.empty:
            t_alvo = st.selectbox("Selecionar Transportadora", ts['nome'].tolist())
            
            if st.button("🚀 Gerar Cotação Completa"):
                t_row = ts[ts['nome'] == t_alvo].iloc[0]
                df_tab = pd.read_json(io.StringIO(t_row['tabela_json']))
                df_cid_ref = pd.read_json(io.StringIO(t_row['cidades_json']))
                mapa_t = json.loads(t_row['mapeamento_json'])
                
                res_final = []
                resumo_uf = {}

                for _, nf in df_b.iterrows():
                    v_total = 0.0
                    try:
                        cidade_nf = str(nf[b_cid]).upper().strip()
                        peso_nf = float(nf[b_peso])
                        valor_nf = float(nf[b_val])
                        
                        # Sigla -> Tabela
                        sigla = df_cid_ref[df_cid_ref.iloc[:,0].astype(str).str.upper() == cidade_nf].iloc[0, 2]
                        precos = df_tab[df_tab.iloc[:,2] == sigla].iloc[0]
                        
                        # Cálculo Frete Peso + Excedente
                        f_peso_valor = 0
                        ultima_faixa_max = 0
                        for f in mapa_t['faixas']:
                            ultima_faixa_max = f['max']
                            if peso_nf <= f['max'] and f['col'] != "Não mapear":
                                f_peso_valor = float(precos[f['col']])
                                break
                        
                        # Lógica de KG Extra
                        if peso_nf > ultima_faixa_max and mapa_t.get("kg_extra") != "Não mapear":
                            base_ultimo = float(precos[mapa_t['faixas'][-1]['col']])
                            valor_kg_extra = float(precos[mapa_t['kg_extra']])
                            f_peso_valor = base_ultimo + ((peso_nf - ultima_faixa_max) * valor_kg_extra)
                        
                        v_total = f_peso_valor
                        # Soma taxas simples (Ad Valorem, etc)
                        if mapa_t['taxas'].get("Ad Valorem %") != "Não mapear":
                            v_total += valor_nf * (float(precos[mapa_t['taxas']["Ad Valorem %"]]) / 100)

                    except: v_total = 0.0
                    
                    nf['FRETE_CALCULADO'] = v_total
                    res_final.append(nf.to_dict())
                    uf = nf[b_uf]
                    resumo_uf[uf] = resumo_uf.get(uf, 0) + v_total

                df_resultado = pd.DataFrame(res_final)
                resumo_json = [{"UF": k, "Transportadora": t_alvo, "Valor": v} for k, v in resumo_uf.items()]
                
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT INTO cotacoes (data_hora, transportadora, total, qtd, detalhes_json, estado_resumo) VALUES (?,?,?,?,?,?)",
                             (datetime.now().strftime("%d/%m - %H:%M"), t_alvo, df_resultado['FRETE_CALCULADO'].sum(), len(df_resultado), df_resultado.to_json(), json.dumps(resumo_json)))
                conn.commit(); conn.close()
                st.success("Concluído!"); st.rerun()

    st.divider()
    conn = sqlite3.connect(DB_NAME)
    df_h = pd.read_sql_query("SELECT * FROM cotacoes ORDER BY id DESC", conn)
    conn.close()
    for _, row in df_h.iterrows():
        with st.expander(f"📦 {row['transportadora']} | {row['data_hora']} | R$ {row['total']:,.2f}"):
            df_det = pd.read_json(io.StringIO(row['detalhes_json']))
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
                df_det.to_excel(writer, index=False)
            st.download_button("📥 Baixar Planilha", out.getvalue(), f"cota_{row['id']}.xlsx")
            if st.button("Deletar", key=f"d_{row['id']}"):
                conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM cotacoes WHERE id=?", (row['id'],)); conn.commit(); conn.close(); st.rerun()
