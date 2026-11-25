"""Cria e popula o banco SQLite com os arquivos disponíveis em ``bd``."""

from pathlib import Path
import re
import sqlite3
import csv
import unicodedata


PASTA_BD = Path(__file__).resolve().parent
CAMINHO_BANCO = PASTA_BD.parent / "database.db"


def padronizar_colunas(colunas):
    return [
        str(col).strip().lower().replace("\ufeff", "").replace(" ", "_")
        .replace("á", "a").replace("ã", "a").replace("í", "i")
        .replace("ú", "u").replace("é", "e").replace("ê", "e")
        .replace("ó", "o").replace("ç", "c")
        for col in colunas
    ]


def arquivos_por_ano(pasta, prefixo):
    """Retorna arquivos por ano; ignora CSVs vazios e usa .part como fallback."""
    encontrados = {}
    padrao = re.compile(
        rf"^{re.escape(prefixo)}_(\d{{4}})(?:\.[^.]+)?\.csv(?:\.part)?$"
    )

    for caminho in pasta.iterdir():
        correspondencia = padrao.match(caminho.name)
        if not correspondencia or caminho.stat().st_size == 0:
            continue
        ano = int(correspondencia.group(1))
        atual = encontrados.get(ano)
        # Prefere CSV final; quando estiver ausente ou vazio, aceita o .part.
        if atual is None or (caminho.suffix == ".csv" and atual.suffix != ".csv"):
            encontrados[ano] = caminho

    return [encontrados[ano] for ano in sorted(encontrados)]


def importa_arquivos(conn, tabela, pasta, prefixo, colunas_esperadas):
    conn.execute(f'DELETE FROM "{tabela}"')
    total = 0
    arquivos = arquivos_por_ano(pasta, prefixo)

    for caminho in arquivos:
        print(f"Importando: {caminho.name}")
        try:
            with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
                leitor = csv.reader(arquivo, delimiter=";")
                cabecalhos = padronizar_colunas(next(leitor))
                indices = {coluna: indice for indice, coluna in enumerate(cabecalhos)}
            ausentes = [col for col in colunas_esperadas if col not in indices]
            if ausentes:
                raise ValueError(f"Colunas ausentes: {', '.join(ausentes)}")
            ordem = [indices[coluna] for coluna in colunas_esperadas]
            placeholders = ",".join("?" for _ in colunas_esperadas)
            with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
                leitor = csv.reader(arquivo, delimiter=";")
                next(leitor)
                lote = []
                for linha in leitor:
                    if not linha:
                        continue
                    linha += [""] * max(0, len(cabecalhos) - len(linha))
                    lote.append(tuple(linha[indice] for indice in ordem))
                    if len(lote) >= 5000:
                        conn.executemany(
                            f'INSERT INTO "{tabela}" VALUES ({placeholders})', lote
                        )
                        total += len(lote)
                        lote.clear()
                if lote:
                    conn.executemany(
                        f'INSERT INTO "{tabela}" VALUES ({placeholders})', lote
                    )
                    total += len(lote)
        except Exception as erro:
            raise RuntimeError(f"Falha ao importar {caminho}: {erro}") from erro

    print(f"{tabela}: {total} registros importados de {len(arquivos)} arquivos.")


def cria_tabelas(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS violenciaSES (
        DT_NOTIFIC TEXT, DT_NASC TEXT, NU_IDADE_N TEXT, CS_SEXO TEXT,
        CS_RACA TEXT, ID_MN_RESI TEXT, LOCAL_OCOR TEXT, OUT_VEZES TEXT,
        LES_AUTOP TEXT, VIOL_FISIC TEXT, VIOL_PSICO TEXT, VIOL_SEXU TEXT,
        NUM_ENVOLV TEXT, AUTOR_SEXO TEXT, ORIENT_SEX TEXT, IDENT_GEN TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS feminicidio (
        municipio_cod TEXT, municipio_fato TEXT, data_fato TEXT, mes TEXT,
        ano TEXT, risp TEXT, rmbh TEXT, tentado_consumado TEXT,
        qtde_vitimas TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS violenciaPc (
        municipio_cod TEXT, municipio_fato TEXT, data_fato TEXT, mes TEXT,
        ano TEXT, risp TEXT, rmbh TEXT, natureza_delito TEXT,
        tentado_consumado TEXT, qtde_vitimas TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS dimensao_municipio (
        municipio_cod TEXT PRIMARY KEY,
        municipio_nome TEXT NOT NULL,
        municipio_ses TEXT,
        classificacao TEXT NOT NULL
    )""")


def chave_municipio(nome):
    sem_acentos = unicodedata.normalize("NFKD", nome or "")
    return "".join(
        caractere for caractere in sem_acentos.upper()
        if caractere.isalnum() and not unicodedata.combining(caractere)
    )


def popula_dimensao_municipio(conn):
    """Relaciona municípios da PC aos nomes da SES e classifica a região."""
    nomes_ses = {}
    for (nome,) in conn.execute(
        "SELECT DISTINCT ID_MN_RESI FROM violenciaSES WHERE TRIM(ID_MN_RESI) <> ''"
    ):
        nomes_ses.setdefault(chave_municipio(nome), nome)
    aliases_ses = {
        "CAPITAOENEIAS": "Capitão Enéas",
        "DONAEUSEBIA": "Dona Euzébia",
        "GOUVEIA": "Gouvêa",
        "QUELUZITO": "Queluzita",
        "AMPARODASERRA": "Amparo do Serra",
        "BARAODOMONTEALTO": "Barão de Monte Alto",
        "ONCADOPITANGUI": "Onça de Pitangui",
        "SAOJOAOBATISTAGLORIA": "São João Batista do Glória",
        "SAOSEBASTDOMARANHAO": "São Sebastião do Maranhão",
        "SAOSEBDORIOPRETO": "São Sebastião do Rio Preto",
        "SAOSEBASTIAOPARAISO": "São Sebastião do Paraíso",
        "SANTARITADOIBITIPOCA": "Santa Rita de Ibitipoca",
        "SAOTOMEDASLETRAS": "São Thomé das Letras",
        "COUTODEMAGDEMINAS": "Couto de Magalhães de Minas",
        "SANTOANTDOAMPARO": "Santo Antônio do Amparo",
    }
    # Chaves removem espaços e pontuação; normaliza os aliases da mesma forma.
    aliases_ses = {chave_municipio(k): v for k, v in aliases_ses.items()}

    municipios = {}
    consulta = conn.execute(
        "SELECT municipio_cod, municipio_fato, rmbh FROM violenciaPc "
        "WHERE TRIM(COALESCE(municipio_cod, '')) <> '' "
        "GROUP BY municipio_cod, municipio_fato, rmbh"
    )
    for codigo, nome, rmbh in consulta:
        if not nome:
            continue
        classificacao_bruta = (rmbh or "").upper()
        if "BELO HORIZONTE" in classificacao_bruta:
            classificacao = "Belo Horizonte"
        elif "RMBH" in classificacao_bruta:
            classificacao = "RMBH"
        else:
            classificacao = "Interior de MG"
        # Em caso de rótulos históricos diferentes, o agrupamento mantém a
        # classificação mais específica para BH/RMBH.
        atual = municipios.get(str(codigo))
        prioridade = {"Interior de MG": 0, "RMBH": 1, "Belo Horizonte": 2}
        if atual is None or prioridade[classificacao] > prioridade[atual[2]]:
            chave = chave_municipio(nome)
            municipio_ses = nomes_ses.get(chave)
            if municipio_ses is None and chave in aliases_ses:
                nome_alias = aliases_ses[chave]
                municipio_ses = nomes_ses.get(chave_municipio(nome_alias))
            municipios[str(codigo)] = (nome, municipio_ses, classificacao)

    conn.execute("DELETE FROM dimensao_municipio")
    conn.executemany(
        "INSERT INTO dimensao_municipio "
        "(municipio_cod, municipio_nome, municipio_ses, classificacao) "
        "VALUES (?, ?, ?, ?)",
        [(codigo, *dados) for codigo, dados in municipios.items()],
    )
    sem_ses = sum(dados[1] is None for dados in municipios.values())
    print(
        f"dimensao_municipio: {len(municipios)} municípios; "
        f"{sem_ses} sem correspondência por nome na SES."
    )


def main():
    colunas_ses = [
        "dt_notific", "dt_nasc", "nu_idade_n", "cs_sexo", "cs_raca",
        "id_mn_resi", "local_ocor", "out_vezes", "les_autop", "viol_fisic",
        "viol_psico", "viol_sexu", "num_envolv", "autor_sexo", "orient_sex",
        "ident_gen",
    ]
    colunas_feminicidio = [
        "municipio_cod", "municipio_fato", "data_fato", "mes", "ano",
        "risp", "rmbh", "tentado_consumado", "qtde_vitimas",
    ]
    colunas_violencia_pc = colunas_feminicidio.copy()
    colunas_violencia_pc.insert(7, "natureza_delito")

    with sqlite3.connect(CAMINHO_BANCO) as conn:
        cria_tabelas(conn)
        importa_arquivos(
            conn, "violenciaSES", PASTA_BD / "violenciaSES",
            "dados_violencia_mulheres_ses", colunas_ses,
        )
        conn.commit()
        importa_arquivos(
            conn, "feminicidio", PASTA_BD / "violenciaPC" / "feminicidio",
            "feminicidio", colunas_feminicidio,
        )
        conn.commit()
        importa_arquivos(
            conn, "violenciaPc", PASTA_BD / "violenciaPC" / "violencia",
            "violencia_domestica", colunas_violencia_pc,
        )
        conn.commit()
        popula_dimensao_municipio(conn)
        conn.commit()

    print(f"Importação concluída: {CAMINHO_BANCO}")


if __name__ == "__main__":
    main()
