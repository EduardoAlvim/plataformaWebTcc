import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import unicodedata
import streamlit as st

titulos = {
        "feminicidio": "Feminicídio (Polícia Civil)",
        "violenciaPc": "Violência contra Mulher (Polícia Civil)",
        "violenciaSES": "Violência contra Mulher (SES)"
    }
# Dicionário para mapear números dos meses para nomes
nomes_meses = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

def normalizar_cidade(nome):
    if not isinstance(nome, str):
        return ""
    nome = unicodedata.normalize('NFKD', nome)
    nome = ''.join(c for c in nome if not unicodedata.combining(c))
    return nome.upper()


def normalizar_periodo(df, coluna, minimo, maximo):
    """Converte período numérico e descarta datas vazias ou malformadas."""
    valores = pd.to_numeric(df[coluna], errors="coerce")
    validos = valores.notna() & valores.between(minimo, maximo)
    df = df.loc[validos].copy()
    df[coluna] = valores.loc[validos].astype(int)
    return df


REGIOES = {"Interior de MG", "RMBH", "Belo Horizonte"}


def aplicar_filtro(query, tabela, filtro):
    if not filtro:
        return query, ()

    if filtro in REGIOES:
        if tabela == "violenciaSES":
            condicao = (
                "ID_MN_RESI IN (SELECT municipio_ses FROM dimensao_municipio "
                "WHERE classificacao = ? AND municipio_ses IS NOT NULL)"
            )
        else:
            condicao = (
                "municipio_cod IN (SELECT municipio_cod FROM dimensao_municipio "
                "WHERE classificacao = ?)"
            )
        parametro = filtro
    elif tabela == "violenciaSES":
        condicao, parametro = "ID_MN_RESI = ?", filtro
    else:
        condicao = (
            "municipio_cod IN (SELECT municipio_cod FROM dimensao_municipio "
            "WHERE REPLACE(REPLACE(municipio_nome, '-', ''), ' ', '') = "
            "REPLACE(REPLACE(?, '-', ''), ' ', ''))"
        )
        parametro = normalizar_cidade(filtro)

    if "WHERE 1=1" in query:
        query = query.replace("WHERE 1=1", f"WHERE 1=1 AND {condicao}", 1)
    elif "GROUP BY" in query:
        query = query.replace("GROUP BY", f"WHERE {condicao} GROUP BY", 1)
    else:
        query += f" WHERE {condicao}"
    return query, (parametro,)


def gerar_grafico_anual_tabela(nome_tabela: str, cidade: str):
    conexao = sqlite3.connect("database.db")
    if nome_tabela == "feminicidio":
        query = """
            SELECT ano, COUNT(*) as total
            FROM feminicidio
            WHERE 1=1
            GROUP BY ano
        """
    elif nome_tabela == "violenciaPc":
        query = """
            SELECT ano, COUNT(*) as total
            FROM violenciaPc
            WHERE 1=1
            GROUP BY ano
        """
    elif nome_tabela == "violenciaSES":
        query = """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 1, 4)
                ELSE substr(trim(DT_NOTIFIC), -4)
            END as ano, COUNT(*) as total
            FROM violenciaSES
            WHERE 1=1
            GROUP BY ano
        """
    else:
        print("Tabela desconhecida.")
        conexao.close()
        return

    # Normaliza cidade para tabelas que precisam
    query, params = aplicar_filtro(query, nome_tabela, cidade)
    df = pd.read_sql_query(query, conexao, params=params)
    df = normalizar_periodo(df, "ano", 1900, 2100)
    if df.empty:
        conexao.close()
        return st.write(f"Não há registros na tabela '{titulos.get(nome_tabela)}' para a cidade '{cidade}'.")

    df = df.sort_values(by="ano", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["ano"], df["total"], marker='o', linestyle='-', color='skyblue')
    ax.set_xlabel("Ano")
    ax.set_ylabel("Número de Crimes")

    ax.set_title(f"Gráfico Anual - Crimes contra a mulher em {cidade} - {titulos.get(nome_tabela)}")
    ax.set_xticks(df["ano"])  # Mostra todos os anos no eixo x
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()

def gerar_grafico_mensal_tabela(nome_tabela: str, cidade: str):
    conexao = sqlite3.connect("database.db")
    if nome_tabela == "feminicidio":
        query = """
            SELECT mes, COUNT(*) as total
            FROM feminicidio
            WHERE 1=1
            GROUP BY mes
        """
    elif nome_tabela == "violenciaPc":
        query = """
            SELECT mes, COUNT(*) as total
            FROM violenciaPc
            WHERE 1=1
            GROUP BY mes
        """
    elif nome_tabela == "violenciaSES":
        query = """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 6, 2)
                ELSE substr(trim(DT_NOTIFIC), 4, 2)
            END as mes, COUNT(*) as total
            FROM violenciaSES
            WHERE 1=1
            GROUP BY mes
        """
    else:
        print("Tabela desconhecida.")
        conexao.close()
        return

    # Normaliza cidade para tabelas que precisam
    query, params = aplicar_filtro(query, nome_tabela, cidade)
    df = pd.read_sql_query(query, conexao, params=params)
    df = normalizar_periodo(df, "mes", 1, 12)
    if df.empty:
        conexao.close()
        return st.write(f"Não há registros na tabela '{titulos.get(nome_tabela)}' para a cidade '{cidade}'.")

    df = df.sort_values(by="mes", ascending=True)
    df["mes_nome"] = df["mes"].map(nomes_meses)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["mes_nome"], df["total"], marker='o', linestyle='-', color='skyblue')
    ax.set_xlabel("Meses")
    ax.set_ylabel("Número de Crimes")

    ax.set_title(f"Gráfico Mensal - Crimes contra a mulher em {cidade} - {titulos.get(nome_tabela)}")
    ax.set_xticks(df["mes_nome"])  
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()

def gerar_grafico_geral_anual(cidade: str):
    conexao = sqlite3.connect("database.db")
    consultas = {
        "feminicidio": """
            SELECT ano, COUNT(*) as total
            FROM feminicidio
            WHERE 1=1
            GROUP BY ano
        """,
        "violenciaPc": """
            SELECT ano, COUNT(*) as total
            FROM violenciaPc
            WHERE 1=1
            GROUP BY ano
        """,
        "violenciaSES": """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 1, 4)
                ELSE substr(trim(DT_NOTIFIC), -4)
            END as ano, COUNT(*) as total
            FROM violenciaSES
            WHERE 1=1
            GROUP BY ano
        """
    }

    total_geral = {}

    for tabela, query in consultas.items():
        query, params = aplicar_filtro(query, tabela, cidade)
        df = pd.read_sql_query(query, conexao, params=params)
        df = normalizar_periodo(df, "ano", 1900, 2100)

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
    ax.set_title(f"Gráfico Anual - Total de crimes contra a mulher em {cidade} (todas as tabelas)")
    ax.set_xticks(df_geral["ano"])
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()


def gerar_grafico_geral_mensal(cidade: str):
    conexao = sqlite3.connect("database.db")
    consultas = {
        "feminicidio": """
            SELECT mes, COUNT(*) as total
            FROM feminicidio
            WHERE 1=1
            GROUP BY mes
        """,
        "violenciaPc": """
            SELECT mes, COUNT(*) as total
            FROM violenciaPc
            WHERE 1=1
            GROUP BY mes
        """,
        "violenciaSES": """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 6, 2)
                ELSE substr(trim(DT_NOTIFIC), 4, 2)
            END as mes, COUNT(*) as total
            FROM violenciaSES
            WHERE 1=1
            GROUP BY mes
        """
    }

    total_geral = {}

    for tabela, query in consultas.items():
        query, params = aplicar_filtro(query, tabela, cidade)
        df = pd.read_sql_query(query, conexao, params=params)
        df = normalizar_periodo(df, "mes", 1, 12)

        for _, row in df.iterrows():
            mes = int(row["mes"])
            total = int(row["total"])
            total_geral[mes] = total_geral.get(mes, 0) + total

    df_geral = pd.DataFrame(list(total_geral.items()), columns=["mes", "total"])
    if not total_geral:
        conexao.close()
        return st.write(f"Não há registros em nenhuma tabela para a cidade '{cidade}'.")

    df_geral = df_geral.sort_values(by="mes")
    df_geral["mes_nome"] = df_geral["mes"].map(nomes_meses)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df_geral["mes_nome"], df_geral["total"], marker='o', linestyle='-', color='salmon')
    ax.set_xlabel("Meses")
    ax.set_ylabel("Número Total de Crimes")
    ax.set_title(f"Gráfico Mensal - Total de crimes contra a mulher em {cidade} (todas as tabelas)")
    ax.set_xticks(df_geral["mes_nome"])
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()

def gerar_grafico_anual_tabela_mg(nome_tabela: str):
    conexao = sqlite3.connect("database.db")
    if nome_tabela == "feminicidio":
        query = """
            SELECT ano, COUNT(*) as total
            FROM feminicidio
            GROUP BY ano
        """
    elif nome_tabela == "violenciaPc":
        query = """
            SELECT ano, COUNT(*) as total
            FROM violenciaPc
            GROUP BY ano
        """
    elif nome_tabela == "violenciaSES":
        query = """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 1, 4)
                ELSE substr(trim(DT_NOTIFIC), -4)
            END as ano, COUNT(*) as total
            FROM violenciaSES
            GROUP BY ano
        """
    else:
        print("Tabela desconhecida.")
        conexao.close()
        return

    query, params = aplicar_filtro(query, nome_tabela, "")
    df = pd.read_sql_query(query, conexao, params=params)
    df = normalizar_periodo(df, "ano", 1900, 2100)
    if df.empty:
        conexao.close()
        return st.write(f"Não há registros na tabela '{titulos.get(nome_tabela)}' para o estado de Minas Gerais")

    df = df.sort_values(by="ano", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["ano"], df["total"], marker='o', linestyle='-', color='skyblue')
    ax.set_xlabel("Ano")
    ax.set_ylabel("Número de Crimes")

    ax.set_title(f"Gráfico Anual - Crimes contra a mulher em Minas Gerais - {titulos.get(nome_tabela)}")
    ax.set_xticks(df["ano"])  # Mostra todos os anos no eixo x
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()

def gerar_grafico_mensal_tabela_mg(nome_tabela: str):
    conexao = sqlite3.connect("database.db")
    if nome_tabela == "feminicidio":
        query = """
            SELECT mes, COUNT(*) as total
            FROM feminicidio
            GROUP BY mes
        """
    elif nome_tabela == "violenciaPc":
        query = """
            SELECT mes, COUNT(*) as total
            FROM violenciaPc
            GROUP BY mes
        """
    elif nome_tabela == "violenciaSES":
        query = """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 6, 2)
                ELSE substr(trim(DT_NOTIFIC), 4, 2)
            END as mes, COUNT(*) as total
            FROM violenciaSES
            GROUP BY mes
        """
    else:
        print("Tabela desconhecida.")
        conexao.close()
        return

    query, params = aplicar_filtro(query, nome_tabela, "")
    df = pd.read_sql_query(query, conexao, params=params)
    df = normalizar_periodo(df, "mes", 1, 12)
    if df.empty:
        conexao.close()
        return st.write(f"Não há registros na tabela '{titulos.get(nome_tabela)}' para o estado de Minas Gerais")

    df = df.sort_values(by="mes", ascending=True)
    df["mes_nome"] = df["mes"].map(nomes_meses)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["mes_nome"], df["total"], marker='o', linestyle='-', color='skyblue')
    ax.set_xlabel("Meses")
    ax.set_ylabel("Número de Crimes")

    ax.set_title(f"Gráfico Mensal - Crimes contra a mulher em Minas Gerais - {titulos.get(nome_tabela)}")
    ax.set_xticks(df["mes_nome"])  
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()

def gerar_grafico_geral_anual_mg():
    conexao = sqlite3.connect("database.db")
    consultas = {
        "feminicidio": """
            SELECT ano, COUNT(*) as total
            FROM feminicidio
            GROUP BY ano
        """,
        "violenciaPc": """
            SELECT ano, COUNT(*) as total
            FROM violenciaPc
            GROUP BY ano
        """,
        "violenciaSES": """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 1, 4)
                ELSE substr(trim(DT_NOTIFIC), -4)
            END as ano, COUNT(*) as total
            FROM violenciaSES
            GROUP BY ano
        """
    }

    total_geral = {}

    for tabela, query in consultas.items():
        query, params = aplicar_filtro(query, tabela, "")
        df = pd.read_sql_query(query, conexao, params=params)
        df = normalizar_periodo(df, "ano", 1900, 2100)

        for _, row in df.iterrows():
            ano = int(row["ano"])
            total = int(row["total"])
            total_geral[ano] = total_geral.get(ano, 0) + total

    df_geral = pd.DataFrame(list(total_geral.items()), columns=["ano", "total"])
    if not total_geral:
        conexao.close()
        return st.write(f"Não há registros em nenhuma tabela para a o estado de Minas Gerais.")

    df_geral = df_geral.sort_values(by="ano")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df_geral["ano"], df_geral["total"], marker='o', linestyle='-', color='salmon')
    ax.set_xlabel("Ano")
    ax.set_ylabel("Número Total de Crimes")
    ax.set_title(f"Gráfico Anual - Total de crimes contra a mulher em Minas Gerais (todas as tabelas)")
    ax.set_xticks(df_geral["ano"])
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()

def gerar_grafico_geral_mensal_mg():
    conexao = sqlite3.connect("database.db")
    consultas = {
        "feminicidio": """
            SELECT mes, COUNT(*) as total
            FROM feminicidio
            GROUP BY mes
        """,
        "violenciaPc": """
            SELECT mes, COUNT(*) as total
            FROM violenciaPc
            GROUP BY mes
        """,
        "violenciaSES": """
            SELECT CASE
                WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
                    THEN substr(trim(DT_NOTIFIC), 6, 2)
                ELSE substr(trim(DT_NOTIFIC), 4, 2)
            END as mes, COUNT(*) as total
            FROM violenciaSES
            GROUP BY mes
        """
    }

    total_geral = {}

    for tabela, query in consultas.items():
        query, params = aplicar_filtro(query, tabela, "")
        df = pd.read_sql_query(query, conexao, params=params)
        df = normalizar_periodo(df, "mes", 1, 12)

        for _, row in df.iterrows():
            mes = int(row["mes"])
            total = int(row["total"])
            total_geral[mes] = total_geral.get(mes, 0) + total

    df_geral = pd.DataFrame(list(total_geral.items()), columns=["mes", "total"])
    if not total_geral:
        conexao.close()
        return st.write(f"Não há registros em nenhuma tabela para o estado de Minas Gerais.")

    df_geral = df_geral.sort_values(by="mes")
    df_geral["mes_nome"] = df_geral["mes"].map(nomes_meses)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df_geral["mes_nome"], df_geral["total"], marker='o', linestyle='-', color='salmon')
    ax.set_xlabel("Meses")
    ax.set_ylabel("Número Total de Crimes")
    ax.set_title(f"Gráfico Mensal - Total de crimes contra a mulher em Minas Gerais (todas as tabelas)")
    ax.set_xticks(df_geral["mes_nome"])
    ax.grid(True, linestyle='--', alpha=0.5)
    fig.tight_layout()
    st.pyplot(fig)
    conexao.close()
