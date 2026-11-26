import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import unicodedata
import streamlit as st
import numpy as np
import textwrap
from matplotlib.ticker import MaxNLocator

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


def nome_local_exibicao(nome):
    nomes_regioes = {
        "RMBH": "Região Metropolitana de Belo Horizonte",
        "Interior de MG": "Interior de Minas Gerais",
        "Belo Horizonte": "Belo Horizonte",
    }
    return nomes_regioes.get(nome, nome or "Minas Gerais")


def normalizar_periodo(df, coluna, minimo, maximo):
    """Converte período numérico e descarta datas vazias ou malformadas."""
    valores = pd.to_numeric(df[coluna], errors="coerce")
    validos = valores.notna() & valores.between(minimo, maximo)
    df = df.loc[validos].copy()
    df[coluna] = valores.loc[validos].astype(int)
    return df


def _exibir_grafico(fig, ax):
    """Ajusta margens e rótulos dos eixos antes de exibir qualquer gráfico."""
    rotulos_y = [rotulo.get_text() for rotulo in ax.get_yticklabels()]
    if rotulos_y and len(rotulos_y) <= 30:
        rotulos_quebrados = [
            textwrap.fill(rotulo, width=28, break_long_words=True)
            for rotulo in rotulos_y
        ]
        if rotulos_quebrados != rotulos_y:
            ax.set_yticks(ax.get_yticks(), labels=rotulos_quebrados)
            linhas_rotulos = sum(rotulo.count("\n") + 1 for rotulo in rotulos_quebrados)
            fig.set_figheight(max(fig.get_figheight(), linhas_rotulos * 0.34 + 1.2))

    if ax.get_xlabel() == "Ano":
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    fig.tight_layout(pad=1.3)
    st.pyplot(fig)
    plt.close(fig)


def _rotular_barras(ax, barras, horizontal=False, formato="%d"):
    """Posiciona os valores fora das barras e reserva espaço para eles."""
    ax.bar_label(barras, fmt=formato, padding=4)
    valores = [barra.get_width() if horizontal else barra.get_height() for barra in barras]
    maior = max(valores, default=0)
    if maior > 0:
        limite = maior * 1.25
        if horizontal:
            ax.set_xlim(left=0, right=limite)
        else:
            ax.set_ylim(bottom=0, top=limite)


REGIOES = {"Interior de MG", "RMBH", "Belo Horizonte"}


def aplicar_filtro(query, tabela, filtro):
    if not filtro:
        return query, ()

    if filtro in REGIOES:
        classificacao = (
            "classificacao IN ('RMBH', 'Belo Horizonte')"
            if filtro == "RMBH"
            else "classificacao = ?"
        )
        if tabela == "violenciaSES":
            condicao = (
                "ID_MN_RESI IN (SELECT municipio_ses FROM dimensao_municipio "
                f"WHERE {classificacao} AND municipio_ses IS NOT NULL)"
            )
        else:
            condicao = (
                "municipio_cod IN (SELECT municipio_cod FROM dimensao_municipio "
                f"WHERE {classificacao})"
            )
        parametro = None if filtro == "RMBH" else filtro
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
    return query, () if parametro is None else (parametro,)


def _condicoes_demograficas_ses(filtro, ano, orientacao, identidade, raca):
    ano_notificacao = """CAST(CASE
        WHEN substr(trim(DT_NOTIFIC), 1, 4) GLOB '[0-9][0-9][0-9][0-9]'
            THEN substr(trim(DT_NOTIFIC), 1, 4)
        ELSE substr(trim(DT_NOTIFIC), -4)
    END AS INTEGER)"""
    condicoes = []
    parametros = []
    if ano is not None:
        condicoes.append(f"{ano_notificacao} = ?")
        parametros.append(ano)

    if filtro in REGIOES:
        if filtro == "RMBH":
            condicoes.append(
                "ID_MN_RESI IN (SELECT municipio_ses FROM dimensao_municipio "
                "WHERE classificacao IN ('RMBH', 'Belo Horizonte') "
                "AND municipio_ses IS NOT NULL)"
            )
        else:
            condicoes.append(
                "ID_MN_RESI IN (SELECT municipio_ses FROM dimensao_municipio "
                "WHERE classificacao = ? AND municipio_ses IS NOT NULL)"
            )
            parametros.append(filtro)
    elif filtro:
        condicoes.append("ID_MN_RESI = ?")
        parametros.append(filtro)

    for coluna, valor in (
        ("ORIENT_SEX", orientacao),
        ("IDENT_GEN", identidade),
        ("CS_RACA", raca),
    ):
        if valor is not None:
            condicoes.append(f"COALESCE(TRIM({coluna}), '') = ?")
            parametros.append(valor)

    return (" AND ".join(condicoes) if condicoes else "1=1"), parametros


def gerar_grafico_demografico_ses(
    filtro, ano, dimensao, orientacao=None, identidade=None, raca=None
):
    colunas = {
        "Orientação sexual": "ORIENT_SEX",
        "Identidade de gênero": "IDENT_GEN",
        "Raça/cor": "CS_RACA",
    }
    coluna = colunas[dimensao]
    where, parametros = _condicoes_demograficas_ses(
        filtro, ano, orientacao, identidade, raca
    )
    query = f"""
        SELECT COALESCE(NULLIF(TRIM({coluna}), ''), 'Não informado') AS categoria,
               COUNT(*) AS total
        FROM violenciaSES
        WHERE {where}
        GROUP BY categoria
        ORDER BY total DESC
    """

    with sqlite3.connect("database.db") as conexao:
        df = pd.read_sql_query(query, conexao, params=parametros)
    if df.empty:
        return st.info("Não há notificações SES para essa combinação de período e local.")

    df = df.sort_values("total", ascending=True)
    fig, ax = plt.subplots(figsize=(10, max(4, len(df) * 0.38)))
    barras = ax.barh(df["categoria"], df["total"], color="teal")
    _rotular_barras(ax, barras, horizontal=True)
    ax.set_xlabel("Notificações SES")
    ax.set_ylabel(dimensao)
    periodo = "todo o histórico" if ano is None else str(ano)
    ax.set_title(f"Notificações SES por {dimensao.lower()} — {periodo}")
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    _exibir_grafico(fig, ax)


def gerar_grafico_tipos_violencia_ses(
    filtro, ano, orientacao=None, identidade=None, raca=None
):
    where, parametros = _condicoes_demograficas_ses(
        filtro, ano, orientacao, identidade, raca
    )
    consulta = """
        SELECT
            SUM(CASE WHEN UPPER(TRIM(VIOL_FISIC)) = 'SIM' THEN 1 ELSE 0 END),
            SUM(CASE WHEN UPPER(TRIM(VIOL_PSICO)) = 'SIM' THEN 1 ELSE 0 END),
            SUM(CASE WHEN UPPER(TRIM(VIOL_SEXU)) = 'SIM' THEN 1 ELSE 0 END),
            SUM(CASE WHEN UPPER(TRIM(LES_AUTOP)) = 'SIM' THEN 1 ELSE 0 END)
        FROM violenciaSES
        WHERE {where}
    """.format(where=where)
    with sqlite3.connect("database.db") as conexao:
        valores = conexao.execute(consulta, parametros).fetchone()
    categorias = ["Física", "Psicológica", "Sexual", "Lesão autoprovocada"]
    df = pd.DataFrame({"tipo": categorias, "total": [valor or 0 for valor in valores]})
    if not df["total"].sum():
        return st.info("Não há notificações SES com tipo de violência marcado como 'Sim' para esse período e local.")

    fig, ax = plt.subplots(figsize=(10, 4))
    barras = ax.bar(df["tipo"], df["total"], color=["#4472C4", "#ED7D31", "#A64D79", "#70AD47"])
    _rotular_barras(ax, barras)
    ax.set_ylabel("Notificações SES com o tipo marcado como 'Sim'")
    periodo = "todo o histórico" if ano is None else str(ano)
    ax.set_title(f"Tipos de violência registrados pela SES — {periodo}")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    _exibir_grafico(fig, ax)
    st.caption("Uma notificação pode marcar mais de um tipo; as barras podem se sobrepor e não devem ser somadas.")


def gerar_grafico_natureza_crime_pc(filtro, ano=None):
    query = """
        SELECT COALESCE(NULLIF(TRIM(natureza_delito), ''), 'Não informado') AS categoria,
               SUM(CAST(REPLACE(qtde_vitimas, ',', '.') AS REAL)) AS total
        FROM violenciaPc
        WHERE 1=1 {condicao_ano}
        GROUP BY categoria
        ORDER BY total DESC
        LIMIT 15
    """
    condicao_ano = "" if ano is None else "AND CAST(ano AS INTEGER) = ?"
    query = query.format(condicao_ano=condicao_ano)
    query, params_local = aplicar_filtro(query, "violenciaPc", filtro)
    with sqlite3.connect("database.db") as conexao:
        parametros = (*params_local, *((ano,) if ano is not None else ()))
        df = pd.read_sql_query(query, conexao, params=parametros)
    if df.empty:
        return st.info("Não há vítimas registradas pela Polícia Civil para esse período e local.")

    df = df.sort_values("total", ascending=True)
    fig, ax = plt.subplots(figsize=(11, max(5, len(df) * 0.36)))
    barras = ax.barh(df["categoria"], df["total"], color="slateblue")
    _rotular_barras(ax, barras, horizontal=True, formato="%.0f")
    ax.set_xlabel("Vítimas registradas pela Polícia Civil")
    ax.set_ylabel("Natureza do crime")
    periodo = "todo o histórico" if ano is None else str(ano)
    ax.set_title(f"Principais naturezas de crime registradas pela PC — {periodo}")
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    _exibir_grafico(fig, ax)


def gerar_grafico_relacao_escolaridade_violencia(filtro=""):
    """Mostra associação municipal exploratória para o ano comum de 2022."""
    if filtro and filtro not in REGIOES:
        return st.info("Selecione Minas Gerais ou uma região para comparar vários municípios.")

    conexao = sqlite3.connect("database.db")
    query = """
        SELECT d.municipio_nome,
               100.0 * c.populacao_18mais_superior / NULLIF(c.populacao_18mais, 0)
                   AS superior_completo_pct,
               100000.0 * COALESCE(v.vitimas, 0) / NULLIF(c.populacao_feminina, 0)
                   AS vitimas_por_100mil_mulheres
        FROM dimensao_municipio d
        JOIN indicadores_ibge_censo2022 c USING (municipio_cod)
        LEFT JOIN (
            SELECT municipio_cod,
                   SUM(CAST(REPLACE(qtde_vitimas, ',', '.') AS REAL)) AS vitimas
            FROM violenciaPc
            WHERE CAST(ano AS INTEGER) = 2022
            GROUP BY municipio_cod
        ) v USING (municipio_cod)
        WHERE 1=1
    """
    parametros = ()
    if filtro in REGIOES:
        if filtro == "RMBH":
            query += " AND d.classificacao IN ('RMBH', 'Belo Horizonte')"
        else:
            query += " AND d.classificacao = ?"
            parametros = (filtro,)

    df = pd.read_sql_query(query, conexao, params=parametros)
    conexao.close()
    df = df.dropna(subset=["superior_completo_pct", "vitimas_por_100mil_mulheres"])
    if df.empty:
        return st.info("Não há indicadores suficientes para montar a análise de 2022.")

    x = df["superior_completo_pct"]
    y = df["vitimas_por_100mil_mulheres"]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(x, y, color="teal", alpha=0.55, edgecolors="none")
    if len(df) > 2 and x.nunique() > 1:
        coeficientes = np.polyfit(x, y, 1)
        linha_x = np.linspace(x.min(), x.max(), 100)
        ax.plot(linha_x, np.polyval(coeficientes, linha_x), color="darkorange", linewidth=2)
    ax.set_xlabel("Adultos (18+) com ensino superior completo (%) — Censo 2022")
    ax.set_ylabel("Vítimas registradas na PC por 100 mil mulheres (Censo 2022) — 2022")
    local = nome_local_exibicao(filtro)
    ax.set_title(f"Escolaridade e violência registrada em {local}")
    ax.grid(True, linestyle="--", alpha=0.35)
    _exibir_grafico(fig, ax)
    # Spearman equivale à correlação de Pearson entre os postos. Calcular assim
    # evita a dependência opcional de scipy, que pandas importa internamente.
    correlacao = (
        x.rank(method="average").corr(y.rank(method="average"))
        if len(df) > 2
        else float("nan")
    )
    st.caption(
        f"Associação exploratória entre {len(df)} municípios em 2022. "
        f"Correlação de Spearman: {correlacao:.2f}. A relação observada não demonstra causalidade."
    )


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
        return st.write(f"Não há registros na tabela '{titulos.get(nome_tabela)}' para {nome_local_exibicao(cidade)}.")

    df = df.sort_values(by="ano", ascending=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["ano"], df["total"], marker='o', linestyle='-', color='skyblue')
    ax.set_xlabel("Ano")
    ax.set_ylabel("Número de Crimes")

    ax.set_title(f"Gráfico Anual - Crimes contra a mulher em {nome_local_exibicao(cidade)} - {titulos.get(nome_tabela)}")
    ax.set_xticks(df["ano"])  # Mostra todos os anos no eixo x
    ax.grid(True, linestyle='--', alpha=0.5)
    _exibir_grafico(fig, ax)
    conexao.close()

def gerar_grafico_mensal_tabela(nome_tabela: str, cidade: str, ano=None):
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

    if ano is not None:
        if nome_tabela == "violenciaSES":
            condicao_ano = "CAST(CASE WHEN substr(trim(DT_NOTIFIC),1,4) GLOB '[0-9][0-9][0-9][0-9]' THEN substr(trim(DT_NOTIFIC),1,4) ELSE substr(trim(DT_NOTIFIC),-4) END AS INTEGER) = ?"
        else:
            condicao_ano = "CAST(ano AS INTEGER) = ?"
        query = query.replace("GROUP BY", f"AND {condicao_ano} GROUP BY", 1)

    # Normaliza cidade para tabelas que precisam
    query, params = aplicar_filtro(query, nome_tabela, cidade)
    df = pd.read_sql_query(query, conexao, params=(*params, *((ano,) if ano is not None else ())))
    df = normalizar_periodo(df, "mes", 1, 12)
    if df.empty:
        conexao.close()
        return st.write(f"Não há registros na tabela '{titulos.get(nome_tabela)}' para {nome_local_exibicao(cidade)}.")

    df = df.sort_values(by="mes", ascending=True)
    df["mes_nome"] = df["mes"].map(nomes_meses)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["mes_nome"], df["total"], marker='o', linestyle='-', color='skyblue')
    ax.set_xlabel("Meses")
    ax.set_ylabel("Número de Crimes")

    periodo = f"{ano}" if ano is not None else "todo o histórico"
    ax.set_title(f"Distribuição mensal — {titulos.get(nome_tabela)} em {nome_local_exibicao(cidade)} ({periodo})")
    ax.set_xticks(df["mes_nome"])  
    ax.grid(True, linestyle='--', alpha=0.5)
    _exibir_grafico(fig, ax)
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
        return st.write(f"Não há registros em nenhuma tabela para {nome_local_exibicao(cidade)}.")

    df_geral = df_geral.sort_values(by="ano")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df_geral["ano"], df_geral["total"], marker='o', linestyle='-', color='salmon')
    ax.set_xlabel("Ano")
    ax.set_ylabel("Número Total de Crimes")
    ax.set_title(f"Gráfico Anual - Total de crimes contra a mulher em {nome_local_exibicao(cidade)} (todas as tabelas)")
    ax.set_xticks(df_geral["ano"])
    ax.grid(True, linestyle='--', alpha=0.5)
    _exibir_grafico(fig, ax)
    conexao.close()


def gerar_grafico_geral_mensal(cidade: str, ano=None):
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
        if ano is not None:
            if tabela == "violenciaSES":
                condicao_ano = "CAST(CASE WHEN substr(trim(DT_NOTIFIC),1,4) GLOB '[0-9][0-9][0-9][0-9]' THEN substr(trim(DT_NOTIFIC),1,4) ELSE substr(trim(DT_NOTIFIC),-4) END AS INTEGER) = ?"
            else:
                condicao_ano = "CAST(ano AS INTEGER) = ?"
            query = query.replace("GROUP BY", f"AND {condicao_ano} GROUP BY", 1)
        query, params = aplicar_filtro(query, tabela, cidade)
        parametros = (*params, *((ano,) if ano is not None else ()))
        df = pd.read_sql_query(query, conexao, params=parametros)
        df = normalizar_periodo(df, "mes", 1, 12)

        for _, row in df.iterrows():
            mes = int(row["mes"])
            total = int(row["total"])
            total_geral[mes] = total_geral.get(mes, 0) + total

    df_geral = pd.DataFrame(list(total_geral.items()), columns=["mes", "total"])
    if not total_geral:
        conexao.close()
        return st.write(f"Não há registros em nenhuma tabela para {nome_local_exibicao(cidade)}.")

    df_geral = df_geral.sort_values(by="mes")
    df_geral["mes_nome"] = df_geral["mes"].map(nomes_meses)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df_geral["mes_nome"], df_geral["total"], marker='o', linestyle='-', color='salmon')
    ax.set_xlabel("Meses")
    ax.set_ylabel("Número Total de Crimes")
    periodo = f"{ano}" if ano is not None else "todo o histórico"
    ax.set_title(f"Distribuição mensal — total das fontes em {nome_local_exibicao(cidade)} ({periodo})")
    ax.set_xticks(df_geral["mes_nome"])
    ax.grid(True, linestyle='--', alpha=0.5)
    _exibir_grafico(fig, ax)
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
    _exibir_grafico(fig, ax)
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
    _exibir_grafico(fig, ax)
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
    _exibir_grafico(fig, ax)
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
    _exibir_grafico(fig, ax)
    conexao.close()
