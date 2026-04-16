import streamlit as st
import requests
import json
import time

st.title("🧪 Teste de Múltiplas Linhas")

# Use sempre o link que termina em /exec
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw2stGRESs-l0dJQEd3bKAawtUb8_zRH1i3VIb4DALNSjdjZnked9Lxs97ProouwR0/exec"

st.write("Clique abaixo para preencher 5 linhas de uma vez na planilha.")

if st.button("Enviar 5 Linhas de Teste"):
    for i in range(1, 6):
        # Dados que serão enviados
        payload = {
            "Nome": f"TRANSPORTADORA TESTE {i}",
            "Mapeamento": f"Configuração da linha {i}"
        }
        
        try:
            # Envia o comando
            response = requests.post(SCRIPT_URL, data=json.dumps(payload))
            
            if response.status_code == 200:
                st.success(f"✅ Linha {i} gravada com sucesso!")
            else:
                st.error(f"❌ Falha na linha {i}. Código: {response.status_code}")
                
        except Exception as e:
            st.error(f"Erro técnico na linha {i}: {e}")
        
        # Uma pequena pausa de meio segundo para o Google não bloquear por excesso de velocidade
        time.sleep(0.5)

    st.info("💡 Agora abra sua planilha e veja se as 5 linhas apareceram lá!")
