import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import unicodedata
import streamlit as st

titulos = {
        "crimesViolentos": "Crimes Violentos (Polícia Civil)",
        "feminicidio": "Feminicídio (Polícia Civil)",
        "violenciaPc": "Violência contra Mulher (Polícia Civil)",
        "violenciaSES": "Violência contra Mulher (SES)"
    }

def normalizar_cidade(nome):
    if not isinstance(nome, str):
        return ""
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.upper()


def gerar_grafico_por_tabela(nome_tabela: str, cidade: str):
    conexao = sqlite3.connect("database.db")
    if nome_tabela == "crimesViolentos":
        query = f"""
            SELECT ano, SUM(CAST(registros AS INT)) as total
            FROM crimesViolentos
            WHERE municipio = ?
            GROUP BY ano
        """
    elif nome_tabela == "feminicidio":
        query = """
            SELECT ano, COUNT(*) as total
            FROM feminicidio
            WHERE municipio_fato = ?
            GROUP BY ano
        """
    elif nome_tabela == "violenciaPc":
        query = """
            SELECT ano, COUNT(*) as total
            FROM violenciaPc
            WHERE municipio_fato = ?
            GROUP BY ano
        """
    elif nome_tabela == "violenciaSES":
        query = """
            SELECT substr(DT_NOTIFIC, -4) as ano, COUNT(*) as total
            FROM violenciaSES
            WHERE ID_MN_RESI = ?
            GROUP BY ano
        """
    else:
        print("Tabela desconhecida.")
        conexao.close()
        return

    # Normaliza cidade para tabelas que precisam
    cidade_param = cidade if nome_tabela == "violenciaSES" else normalizar_cidade(cidade)

    df = pd.read_sql_query(query, conexao, params=(cidade_param,))
    df["ano"] = df["ano"].astype(int)
    if df.empty:
        conexao.close()
        return st.write(f"Não há registros na tabela '{titulos.get(nome_tabela)}' para a cidade '{cidade}'.")

    df = df.sort_values(by="ano", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["ano"], df["total"], marker='o', linestyle='-', color='skyblue')
    ax.set_xlabel("Ano")
    ax.set_ylabel("Número de Crimes")

    ax.set_title(f"Crimes contra a mulher em {cidade} - {titulos.get(nome_tabela)}")
    ax.set_xticks(df["ano"])  # Mostra todos os anos no eixo x
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()

def gerar_grafico_geral(cidade: str):
    conexao = sqlite3.connect("database.db")
    consultas = {
        "crimesViolentos": """
        SELECT ano, SUM(CAST(registros AS INT)) as total
        FROM crimesViolentos
        WHERE municipio = ?
        GROUP BY ano
        """,
        "feminicidio": """
            SELECT ano, COUNT(*) as total
            FROM feminicidio
            WHERE municipio_fato = ?
            GROUP BY ano
        """,
        "violenciaPc": """
            SELECT ano, COUNT(*) as total
            FROM violenciaPc
            WHERE municipio_fato = ?
            GROUP BY ano
        """,
        "violenciaSES": """
            SELECT substr(DT_NOTIFIC, -4) as ano, COUNT(*) as total
            FROM violenciaSES
            WHERE ID_MN_RESI = ?
            GROUP BY ano
        """
    }

    total_geral = {}

    for tabela, query in consultas.items():
        cidade_param = cidade if tabela == "violenciaSES" else normalizar_cidade(cidade)
        df = pd.read_sql_query(query, conexao, params=(cidade_param,))
        df["ano"] = df["ano"].astype(int)

        for _, row in df.iterrows():
            ano = int(row["ano"])
            total = int(row["total"])
            total_geral[ano] = total_geral.get(ano, 0) + total

    df_geral = pd.DataFrame(list(total_geral.items()), columns=["ano", "total"])
    if not total_geral:
        conexao.close()
        return st.write(f"Não há registros em nenhuma tabela para a cidade '{cidade}'.")

    df_geral = df_geral.sort_values(by="ano")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df_geral["ano"], df_geral["total"], marker='o', linestyle='-', color='salmon')
    ax.set_xlabel("Ano")
    ax.set_ylabel("Número Total de Crimes")
    ax.set_title(f"Total de crimes contra a mulher em {cidade} (todas as tabelas)")
    ax.set_xticks(df_geral["ano"])  # Mostra todos os anos no eixo x
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()