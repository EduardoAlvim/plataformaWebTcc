"""Baixa indicadores municipais do IBGE e atualiza o banco local."""

import sqlite3
from datetime import date
from pathlib import Path

import requests


PASTA_BD = Path(__file__).resolve().parent
CAMINHO_BANCO = PASTA_BD.parent / "database.db"
BASE_IBGE = "https://servicodados.ibge.gov.br/api"
PESQUISA_IDHM = 37
INDICADOR_IDHM = 30255
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


def indexar_escolaridade_2010(resposta):
    """Agrega os grupos etários adultos da tabela 3540 (Censo 2010)."""
    saida = {}
    faixas_adultas = {"92982", "1144", "1145", "1146", "1147", "1148", "1149", "1150", "1151"}
    for variavel in resposta:
        if str(variavel.get("id")) != "140":
            continue
        for resultado in variavel.get("resultados", []):
            classificacoes = {
                str(item["id"]): next(iter(item["categoria"]))
                for item in resultado.get("classificacoes", [])
            }
            nivel = classificacoes.get("1568")
            idade = classificacoes.get("58")
            if idade not in faixas_adultas:
                continue
            for serie in resultado.get("series", []):
                codigo = str(serie["localidade"]["id"])
                valor = next(iter(serie.get("serie", {}).values()), None)
                try:
                    quantidade = int(float(valor))
                except (TypeError, ValueError):
                    continue
                niveis = saida.setdefault(codigo, {})
                niveis[nivel] = niveis.get(nivel, 0) + quantidade
    return saida


def indexar_total_adultos_2010(resposta):
    """Soma a população adulta sem abrir por nível de instrução."""
    saida = {}
    faixas_adultas = {"92982", "1144", "1145", "1146", "1147", "1148", "1149", "1150", "1151"}
    for variavel in resposta:
        for resultado in variavel.get("resultados", []):
            classificacoes = {
                str(item["id"]): next(iter(item["categoria"]))
                for item in resultado.get("classificacoes", [])
            }
            if classificacoes.get("58") not in faixas_adultas:
                continue
            for serie in resultado.get("series", []):
                codigo = str(serie["localidade"]["id"])
                valor = next(iter(serie.get("serie", {}).values()), None)
                try:
                    saida[codigo] = saida.get(codigo, 0) + int(float(valor))
                except (TypeError, ValueError):
                    continue
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


def extrair_series_idhm(resposta):
    """Lê localidades e anos da resposta da API de Pesquisas do IBGE."""
    series = []

    def percorrer(item):
        if isinstance(item, dict):
            res = item.get("res")
            localidade = item.get("localidade")
            if isinstance(res, dict) and localidade is not None:
                codigo = localidade.get("id") if isinstance(localidade, dict) else localidade
                if codigo is not None:
                    for ano, valor in res.items():
                        try:
                            valor = float(str(valor).replace(",", "."))
                            series.append((str(codigo), int(ano), valor))
                        except (TypeError, ValueError):
                            continue
            for chave, valor in item.items():
                if chave != "res" or not isinstance(res, dict):
                    percorrer(valor)
        elif isinstance(item, list):
            for valor in item:
                percorrer(valor)

    percorrer(resposta)
    return series


def baixar_series_idhm(codigos_por_municipio):
    """Obtém IDH estadual pela API IBGE e IDHM municipal pela API oficial Ipeadata."""
    base_ibge = (
        f"{BASE_IBGE}/v1/pesquisas/{PESQUISA_IDHM}/indicadores/"
        f"{INDICADOR_IDHM}/resultados"
    )
    series = [
        ("MG", ano, valor)
        for codigo, ano, valor in extrair_series_idhm(buscar_json(f"{base_ibge}/31"))
        if codigo == "31"
    ]

    # A rota do IBGE para resultados municipais retorna [] para o indicador 30255.
    # O Ipeadata publica os valores municipais do Atlas (1991, 2000 e 2010) por API OData.
    url_ipeadata = "https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='ADH_IDHM')"
    resposta = SESSAO.get(url_ipeadata, timeout=120)
    resposta.raise_for_status()
    valores = resposta.json().get("value", [])
    codigo_pc_por_ibge = {
        str(codigo_ibge): str(codigo_pc).zfill(6)
        for codigo_pc, codigo_ibge in codigos_por_municipio.items()
    }
    municipios = []
    for registro in valores:
        municipio_cod = codigo_pc_por_ibge.get(str(registro.get("TERCODIGO")))
        data = registro.get("VALDATA", "")
        valor = registro.get("VALVALOR")
        if not municipio_cod or not data or valor is None:
            continue
        try:
            municipios.append((municipio_cod, int(data[:4]), float(valor)))
        except (TypeError, ValueError):
            continue
    if not municipios:
        raise ValueError("A API do Ipeadata não retornou valores municipais de IDHM para Minas Gerais.")
    return series + municipios


def main():
    ano_corrente = date.today().year
    anos_populacao = list(range(2010, min(ano_corrente, 2023) + 1))
    anos_populacao_recentes = (
        list(range(2024, ano_corrente + 1)) if ano_corrente >= 2024 else []
    )
    anos_pib = list(range(2010, ano_corrente + 1))
    with sqlite3.connect(CAMINHO_BANCO) as conn:
        codigos_por_municipio = codigos_ibge_mg(conn)
        conn.commit()
        codigos = list(codigos_por_municipio.values())

        print("Baixando estimativas anuais de população...")
        populacao = indice_series(
            consultar_agregado(6579, anos_populacao, [9324], codigos)
        )
        if anos_populacao_recentes:
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
        print("Baixando população e escolaridade do Censo 2010...")
        populacao_censo_2010 = indice_series(
            consultar_agregado(608, [2010], [93], codigos)
        )
        area_densidade_2010 = indexar_variaveis(
            consultar_agregado(1301, [2010], [615, 616], codigos)
        )
        escolaridade_2010 = indexar_escolaridade_2010(
            consultar_agregado(
                3540, [2010], [140], codigos,
                classificacao="1568[9493,99713]|58[92982,1144,1145,1146,1147,1148,1149,1150,1151]",
            )
        )
        total_adultos_2010 = indexar_total_adultos_2010(
            consultar_agregado(
                3540, [2010], [140], codigos,
                classificacao="58[92982,1144,1145,1146,1147,1148,1149,1150,1151]",
            )
        )
        print("Baixando PIB municipal anual...")
        pib = indice_series(
            consultar_agregado(5938, anos_pib, [37], codigos)
        )
        print("Baixando IDH estadual do IBGE e IDHM municipal do Ipeadata...")
        try:
            series_idhm = baixar_series_idhm(codigos_por_municipio)
        except (requests.RequestException, ValueError, TypeError) as erro:
            series_idhm = []
            print(f"Aviso: não foi possível atualizar o IDHM: {erro}")
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
        conn.execute("""CREATE TABLE IF NOT EXISTS indicadores_ibge_perfil_censitario (
            municipio_cod TEXT NOT NULL,
            ano INTEGER NOT NULL,
            populacao_censo REAL,
            area_km2 REAL,
            densidade_demografica REAL,
            populacao_18mais REAL,
            populacao_18mais_superior REAL,
            populacao_18mais_baixa_escolaridade REAL,
            PRIMARY KEY (municipio_cod, ano)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS indicadores_ibge_per_capita (
            municipio_cod TEXT NOT NULL,
            ano INTEGER NOT NULL,
            valor REAL,
            PRIMARY KEY (municipio_cod, ano)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS indicadores_ibge_idhm (
            municipio_cod TEXT NOT NULL,
            ano INTEGER NOT NULL,
            valor REAL NOT NULL,
            PRIMARY KEY (municipio_cod, ano)
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
        linhas_perfil = []
        for codigo_pc, codigo_ibge in codigos_por_municipio.items():
            niveis_2010 = escolaridade_2010.get(codigo_ibge, {})
            adultos_2010 = total_adultos_2010.get(codigo_ibge)
            linhas_perfil.extend([
                (codigo_pc, 2010, populacao_censo_2010.get((codigo_ibge, 2010)),
                 area_densidade_2010.get((codigo_ibge, "615")),
                 area_densidade_2010.get((codigo_ibge, "616")),
                 adultos_2010, niveis_2010.get("99713"), niveis_2010.get("9493")),
                (codigo_pc, 2022,
                 valores_censo.get((codigo_ibge, "93")),
                 valores_censo.get((codigo_ibge, "6318")),
                 valores_censo.get((codigo_ibge, "614")),
                 escolaridade.get(codigo_ibge, {}).get("120704"),
                 escolaridade.get(codigo_ibge, {}).get("99713"),
                 escolaridade.get(codigo_ibge, {}).get("9493")),
            ])
        conn.execute("DELETE FROM indicadores_ibge_perfil_censitario")
        conn.executemany(
            "INSERT INTO indicadores_ibge_perfil_censitario "
            "(municipio_cod, ano, populacao_censo, area_km2, densidade_demografica, "
            "populacao_18mais, populacao_18mais_superior, populacao_18mais_baixa_escolaridade) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            linhas_perfil,
        )
        if series_idhm:
            conn.executemany(
                "INSERT OR REPLACE INTO indicadores_ibge_idhm "
                "(municipio_cod, ano, valor) VALUES (?, ?, ?)",
                series_idhm,
            )
        conn.commit()

    print(
        f"Indicadores IBGE atualizados para {len(codigos_por_municipio)} municípios. "
        f"População: {resumir_periodos(ano for _, ano in populacao)}; "
        f"PIB: {resumir_periodos(ano for _, ano in pib)}; Censos: 2010 e 2022; "
        f"IDH/IDHM: {len(series_idhm)} registros (estado via IBGE e municípios via Ipeadata)."
    )


if __name__ == "__main__":
    main()
