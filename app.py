try:
    supabase.table("cotacoes").insert({
        "data_hora": data_sao_paulo.strftime("%d/%m/%Y %H:%M"),
        "qtd": len(df_base),
        "detalhes_json": df_final.fillna(0).to_dict(orient='records')
    }).execute()
except Exception as e:
    st.error(f"Erro real do Supabase: {e}")
