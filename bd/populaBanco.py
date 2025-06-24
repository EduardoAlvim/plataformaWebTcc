import os
import sqlite3
import pandas as pd

nome_banco = "database.db"

conn = sqlite3.connect(nome_banco)
cursor = conn.cursor()

def padronizar_colunas(colunas):
    return [
        col.strip().lower()
           .replace('\ufeff', '')
           .replace(" ", "_")
           .replace("á", "a").replace("ã", "a")
           .replace("í", "i").replace("ú", "u")
           .replace("é", "e").replace("ê", "e")
           .replace("ó", "o").replace("ç", "c")
        for col in colunas
    ]

#-------------------TABELA DE VIOLENCIASES-------------------

def populaViolenciaSES():
    pasta_violenciaSES = os.path.join("bd", "violenciaSES")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS violenciaSES (
            DT_NOTIFIC TEXT,
            DT_NASC TEXT,
            NU_IDADE_N TEXT,
            CS_SEXO TEXT,
            CS_RACA TEXT,
            ID_MN_RESI TEXT,
            LOCAL_OCOR TEXT,
            OUT_VEZES TEXT,
            LES_AUTOP TEXT,
            VIOL_FISIC TEXT,
            VIOL_PSICO TEXT,
            VIOL_SEXU TEXT,
            NUM_ENVOLV TEXT,
            AUTOR_SEXO TEXT,
            ORIENT_SEX TEXT,
            IDENT_GEN TEXT
        );
    ''')
    conn.commit()

    colunas_esperadas = padronizar_colunas([
    'DT_NOTIFIC', 'DT_NASC', 'NU_IDADE_N', 'CS_SEXO', 'CS_RACA', 'ID_MN_RESI',
    'LOCAL_OCOR', 'OUT_VEZES', 'LES_AUTOP', 'VIOL_FISIC', 'VIOL_PSICO',
    'VIOL_SEXU', 'NUM_ENVOLV', 'AUTOR_SEXO', 'ORIENT_SEX', 'IDENT_GEN'
    ])

    for ano in range(2010, 2024):
        if ano == 2019:
            nome_arquivo = "dados_violencia_mulheres_ses_2019.q2UgH0k1.csv.part"
        elif ano == 2020:
            nome_arquivo = "dados_violencia_mulheres_ses_2020.CyIvHK1X.csv.part"
        elif ano == 2021:
            nome_arquivo = "dados_violencia_mulheres_ses_2021.Ec3M9c-d.csv.part"
        elif ano == 2022:
            nome_arquivo = "dados_violencia_mulheres_ses_2022.AmKRWFNR.csv.part"
        elif ano == 2023:
            nome_arquivo = "dados_violencia_mulheres_ses_2023.2cTFR8ZU.csv.part"
        else:
            nome_arquivo = f"dados_violencia_mulheres_ses_{ano}.csv"
        
        caminho_arquivo = os.path.join(pasta_violenciaSES, nome_arquivo)

        if os.path.exists(caminho_arquivo):
            print(f"Importando: {nome_arquivo}")
            try:
                df = pd.read_csv(caminho_arquivo, sep=None, engine='python')
                df.columns = padronizar_colunas(df.columns)
                df = df[colunas_esperadas]

                if not df.empty:
                    df.to_sql('violenciaSES', conn, if_exists='append', index=False)
                else:
                    print(f"Nenhum registro encontrado em {nome_arquivo}.")

            except Exception as e:
                print(f"Erro ao importar {nome_arquivo}: {e}")
        else:
            print(f"Arquivo não encontrado: {nome_arquivo}")

#-------------------TABELA DE FEMINICÍDIO-------------------
def populaFeminicidio():
    pasta_feminicidio = os.path.join("bd", "violenciaPC","feminicidio")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feminicidio (
            municipio_cod TEXT,
            municipio_fato TEXT,
            data_fato TEXT,
            mes TEXT,
            ano TEXT,
            risp TEXT,
            rmbh TEXT,
            tentado_consumado TEXT,
            qtde_vitimas TEXT
        );
    ''')
    conn.commit()

    colunas_esperadas = ['municipio_cod','municipio_fato','data_fato','mes','ano','risp','rmbh','tentado_consumado','qtde_vitimas']

    for ano in range(2018, 2024):
        nome_arquivo = f"feminicidio_{ano}.csv"
        
        caminho_arquivo = os.path.join(pasta_feminicidio, nome_arquivo)

        if os.path.exists(caminho_arquivo):
            print(f"Importando: {nome_arquivo}")
            try:
                df = pd.read_csv(caminho_arquivo, sep=None, engine='python')
                df.columns = padronizar_colunas(df.columns)
                df = df[colunas_esperadas]

                if not df.empty:
                    df.to_sql('feminicidio', conn, if_exists='append', index=False)
                else:
                    print(f"Nenhum registro encontrado em {nome_arquivo}.")

            except Exception as e:
                print(f"Erro ao importar {nome_arquivo}: {e}")
        else:
            print(f"Arquivo não encontrado: {nome_arquivo}")

#-------------------TABELA DE VIOLENCIAPC-------------------
def populaViolenciaPc():
    pasta_violenciaPc = os.path.join("bd", "violenciaPC","violencia")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS violenciaPc (
            municipio_cod TEXT,
            municipio_fato TEXT,
            data_fato TEXT,
            mes TEXT,
            ano TEXT,
            risp TEXT,
            rmbh TEXT,
            natureza_delito TEXT,
            tentado_consumado TEXT,
            qtde_vitimas TEXT
        );
    ''')
    conn.commit()

    colunas_esperadas = ['municipio_cod','municipio_fato','data_fato','mes','ano','risp','rmbh','natureza_delito','tentado_consumado','qtde_vitimas']

    for ano in range(2014, 2024):
        if ano == 2014:
            nome_arquivo = "violencia_domestica_2014.psggbeaE.csv.part"
        else:
            nome_arquivo = f"violencia_domestica_{ano}.csv"
        
        caminho_arquivo = os.path.join(pasta_violenciaPc, nome_arquivo)

        if os.path.exists(caminho_arquivo):
            print(f"Importando: {nome_arquivo}")
            try:
                df = pd.read_csv(caminho_arquivo, sep=None, engine='python')
                df.columns = padronizar_colunas(df.columns)
                df = df[colunas_esperadas]

                if not df.empty:
                    df.to_sql('violenciaPc', conn, if_exists='append', index=False)
                else:
                    print(f"Nenhum registro encontrado em {nome_arquivo}.")

            except Exception as e:
                print(f"Erro ao importar {nome_arquivo}: {e}")
        else:
            print(f"Arquivo não encontrado: {nome_arquivo}")

populaViolenciaSES()
populaFeminicidio()
populaViolenciaPc()
conn.close()
print("Importação concluída.")
