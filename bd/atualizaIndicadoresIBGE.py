"""Baixa indicadores municipais do IBGE e atualiza o banco local."""

import sqlite3
from pathlib import Path

import requests


PASTA_BD = Path(__file__).resolve().parent
CAMINHO_BANCO = PASTA_BD.parent / "database.db"
BASE_IBGE = "https://servicodados.ibge.gov.br/api"
SESSAO = requests.Session()
SESSAO.headers.update({"User-Agent": "plataformaWebTcc/1.0 (indicadores municipais)"})


def buscar_json(url, params=None):
    resposta = SESSAO.get(url, params=params, timeout=90)
    resposta.raise_for_status()
    return resposta.json()


def lotes(itens, tamanho=100):
    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio:inicio + tamanho]


def resumir_periodos(anos):
    intervalos = []
    for ano in sorted(set(anos)):
        if not intervalos or ano > intervalos[-1][1] + 1:
            intervalos.append([ano, ano])
        else:
            intervalos[-1][1] = ano
    return ", ".join(
        str(inicio) if inicio == fim else f"{inicio}–{fim}"
        for inicio, fim in intervalos
    )


def codigos_ibge_mg(conn):
    localidades = buscar_json(f"{BASE_IBGE}/v1/localidades/estados/31/municipios")
    codigos_pc = {
        str(codigo).zfill(6)
        for (codigo,) in conn.execute("SELECT municipio_cod FROM dimensao_municipio")
    }
    por_codigo_pc = {}
    for municipio in localidades:
        codigo_ibge = str(municipio["id"])
        codigo_pc = codigo_ibge[:6]
        if codigo_pc in codigos_pc:
            por_codigo_pc[codigo_pc] = codigo_ibge

    ausentes = codigos_pc - por_codigo_pc.keys()
    if ausentes:
        raise RuntimeError(
            f"A API do IBGE não retornou códigos para {len(ausentes)} municípios da dimensão."
        )

    colunas = {linha[1] for linha in conn.execute("PRAGMA table_info(dimensao_municipio)")}
    if "codigo_ibge" not in colunas:
        conn.execute("ALTER TABLE dimensao_municipio ADD COLUMN codigo_ibge TEXT")
    conn.executemany(
        "UPDATE dimensao_municipio SET codigo_ibge = ? WHERE municipio_cod = ?",
        [(codigo_ibge, codigo_pc) for codigo_pc, codigo_ibge in por_codigo_pc.items()],
    )
    return por_codigo_pc


def consultar_agregado(agregado, periodos, variaveis, codigos, classificacao=None):
    periodo_path = "|".join(str(periodo) for periodo in periodos)
    variavel_path = "|".join(str(variavel) for variavel in variaveis)
    url = f"{BASE_IBGE}/v3/agregados/{agregado}/periodos/{periodo_path}/variaveis/{variavel_path}"
    resultado = []

    for lote in lotes(codigos):
        params = {"localidades": f"N6[{','.join(lote)}]"}
        if classificacao:
            params["classificacao"] = classificacao
        resultado.extend(buscar_json(url, params=params))
    return resultado


def indice_series(resposta):
    """Transforma a resposta da API em (código IBGE, período) -> valor."""
    saida = {}
    for variavel in resposta:
        for resultado in variavel.get("resultados", []):
            for serie in resultado.get("series", []):
                codigo = str(serie["localidade"]["id"])
                for periodo, valor in serie.get("serie", {}).items():
                    if valor not in (None, "", "..."):
                        try:
                            saida[(codigo, int(periodo))] = float(valor)
                        except (TypeError, ValueError):
                            continue
    return saida


def indexar_censo(resposta):
    saida = {}
    for variavel in resposta:
        if str(variavel.get("id")) != "2667":
            continue
        for resultado in variavel.get("resultados", []):
            for serie in resultado.get("series", []):
                codigo = str(serie["localidade"]["id"])
                classificacoes = {
                    str(item["id"]): next(iter(item["categoria"]))
                    for item in resultado.get("classificacoes", [])
                }
                nivel = classificacoes.get("1568")
                valor = next(iter(serie.get("serie", {}).values()), None)
                try:
                    quantidade = int(float(valor))
                except (TypeError, ValueError):
                    continue
                dados = saida.setdefault(codigo, {})
                dados[nivel] = quantidade
    return saida


def indexar_variaveis(resposta):
    saida = {}
    for variavel in resposta:
        variavel_id = str(variavel.get("id"))
        for resultado in variavel.get("resultados", []):
            for serie in resultado.get("series", []):
                codigo = str(serie["localidade"]["id"])
                valor = next(iter(serie.get("serie", {}).values()), None)
                try:
                    saida[(codigo, variavel_id)] = float(valor)
                except (TypeError, ValueError):
                    continue
    return saida


def main():
    anos_populacao = list(range(2010, 2024))
    anos_populacao_recentes = [2024, 2025, 2026]
    anos_pib = list(range(2010, 2024))
    with sqlite3.connect(CAMINHO_BANCO) as conn:
        codigos_por_municipio = codigos_ibge_mg(conn)
        conn.commit()
        codigos = list(codigos_por_municipio.values())

        print("Baixando estimativas anuais de população...")
        populacao = indice_series(
            consultar_agregado(6579, anos_populacao, [9324], codigos)
        )
        populacao.update(indice_series(
            consultar_agregado(6579, anos_populacao_recentes, [9324], codigos)
        ))
        print("Baixando população, área e densidade do Censo 2022...")
        resposta_censo = consultar_agregado(4714, [2022], [93, 6318, 614], codigos)
        valores_censo = indexar_variaveis(resposta_censo)
        print("Baixando população feminina do Censo 2022...")
        mulheres_censo = indexar_variaveis(
            consultar_agregado(
                9514,
                [2022],
                [93],
                codigos,
                classificacao="2[5]|287[100362]|286[113635]",
            )
        )
        print("Baixando distribuição de escolaridade do Censo 2022...")
        escolaridade = indexar_censo(
            consultar_agregado(
                10061,
                [2022],
                [2667],
                codigos,
                classificacao="1568[120704,9493,9494,9495,99713]|"
                "58[95253]|2[6794]|86[95251]",
            )
        )
        print("Baixando PIB municipal anual...")
        pib = indice_series(
            consultar_agregado(5938, anos_pib, [37], codigos)
        )

        conn.execute("""CREATE TABLE IF NOT EXISTS indicadores_ibge_anual (
            municipio_cod TEXT NOT NULL,
            ano INTEGER NOT NULL,
            populacao_estimada REAL,
            pib_mil_reais REAL,
            PRIMARY KEY (municipio_cod, ano)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS indicadores_ibge_censo2022 (
            municipio_cod TEXT PRIMARY KEY,
            populacao_censo REAL,
            area_km2 REAL,
            densidade_demografica REAL,
            populacao_18mais REAL,
            populacao_18mais_superior REAL,
            populacao_18mais_baixa_escolaridade REAL,
            populacao_feminina REAL
        )""")
        colunas_censo = {
            linha[1] for linha in conn.execute("PRAGMA table_info(indicadores_ibge_censo2022)")
        }
        if "populacao_feminina" not in colunas_censo:
            conn.execute(
                "ALTER TABLE indicadores_ibge_censo2022 "
                "ADD COLUMN populacao_feminina REAL"
            )

        por_municipio = {}
        for codigo_pc, codigo_ibge in codigos_por_municipio.items():
            anos = set(anos_populacao) | set(anos_populacao_recentes) | set(anos_pib)
            for ano in anos:
                por_municipio[(codigo_pc, ano)] = (
                    populacao.get((codigo_ibge, ano)),
                    pib.get((codigo_ibge, ano)),
                )

        conn.execute("DELETE FROM indicadores_ibge_anual")
        conn.executemany(
            "INSERT INTO indicadores_ibge_anual "
            "(municipio_cod, ano, populacao_estimada, pib_mil_reais) VALUES (?, ?, ?, ?)",
            [(codigo, ano, valores[0], valores[1])
             for (codigo, ano), valores in por_municipio.items()],
        )

        conn.execute("DELETE FROM indicadores_ibge_censo2022")
        linhas_censo = []
        for codigo_pc, codigo_ibge in codigos_por_municipio.items():
            niveis = escolaridade.get(codigo_ibge, {})
            linhas_censo.append((
                codigo_pc,
                valores_censo.get((codigo_ibge, "93")),
                valores_censo.get((codigo_ibge, "6318")),
                valores_censo.get((codigo_ibge, "614")),
                niveis.get("120704"),
                niveis.get("99713"),
                niveis.get("9493"),
                mulheres_censo.get((codigo_ibge, "93")),
            ))
        conn.executemany(
            "INSERT INTO indicadores_ibge_censo2022 "
            "(municipio_cod, populacao_censo, area_km2, densidade_demografica, "
            "populacao_18mais, populacao_18mais_superior, "
            "populacao_18mais_baixa_escolaridade, populacao_feminina) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            linhas_censo,
        )
        conn.commit()

    print(
        f"Indicadores IBGE atualizados para {len(codigos_por_municipio)} municípios. "
        f"População: {resumir_periodos(ano for _, ano in populacao)}; "
        f"PIB: {resumir_periodos(ano for _, ano in pib)}; Censo: 2022."
    )


if __name__ == "__main__":
    main()
