import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

@st.cache_data
def cargar_txt_crep(archivo_txt):
    lineas = archivo_txt.read().decode('utf-8').splitlines()
    registros = []
    for linea in lineas:
        if linea.startswith('DD'):
            try:
                psp_tin = linea[205:217].strip().lstrip("0")
                monto_raw = linea[73:88].strip()
                monto = int(monto_raw) / 100 if monto_raw.isdigit() else None
                medio_atencion = linea[156:168].strip()
                anio = linea[57:61]
                mes = linea[61:63]
                dia = linea[63:65]
                fecha_pago = f"{dia}/{mes}/{anio}"
                hora = linea[168:170]
                minuto = linea[170:172]
                segundo = linea[172:174]
                hora_pago = f"{hora}:{minuto}:{segundo}"
                fecha_hora_pago = datetime.strptime(
                    f"{dia}/{mes}/{anio} {hora}:{minuto}:{segundo}",
                    "%d/%m/%Y %H:%M:%S"
                )
                nro_operacion = linea[124:130].strip()
                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha': fecha_pago,
                    'Hora': hora_pago,
                    'FechaHora': fecha_hora_pago,
                    'Nº operación': nro_operacion
                })
            except:
                continue
    df = pd.DataFrame(registros)
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    return df.drop_duplicates(subset='PSP_TIN'), True


@st.cache_data
def cargar_excel_bcp(archivo):
    df = pd.read_excel(archivo, skiprows=7)
    df['Descripción operación'] = df['Descripción operación'].astype(str).str.strip()
    df['Nº operación'] = df['Nº operación'].astype(str).str.strip()
    df['Monto'] = pd.to_numeric(df['Monto'], errors='coerce')
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df['PSP_TIN'] = df['Descripción operación'].str.extract(r'(2\d{11})(?!\d)', expand=False)

    duplicados = df[df.duplicated(subset=['Nº operación'], keep=False)]
    extornos = duplicados['Descripción operación'].str.contains('Extorno', case=False, na=False)
    numeros_extorno = duplicados[extornos]['Nº operación'].unique()
    df_filtrado = df[~df['Nº operación'].isin(numeros_extorno)]

    df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')

    return df_filtrado[['PSP_TIN', 'Monto', 'Fecha', 'Nº operación']], False


@st.cache_data
def cargar_excel_bbva(archivo):
    # Saltamos las 10 primeras filas del reporte BBVA (encabezados y filtros)
    df = pd.read_excel(archivo, skiprows=10)
    # Limpiar espacios en los nombres de columna
    df.columns = df.columns.str.strip()

    # Columnas esperadas del formato BBVA
    col_fecha = 'F.Operación'
    col_concepto = 'Concepto'
    col_nro_op = 'Núm.Movimiento'
    col_importe = 'Importe'

    # Limpieza básica
    df[col_concepto] = df[col_concepto].astype(str).str.strip()
    df[col_nro_op] = df[col_nro_op].astype(str).str.strip()

    # Monto y fecha
    df['Monto'] = pd.to_numeric(df[col_importe], errors='coerce')
    # Formato típico: 11-12-2025
    df['Fecha'] = pd.to_datetime(df[col_fecha], format='%d-%m-%Y', errors='coerce')

    # Extraer PSP_TIN desde Concepto (12 dígitos que_
