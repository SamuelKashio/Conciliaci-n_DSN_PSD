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

    # Extraer PSP_TIN desde Concepto (12 dígitos que empiezan con 2)
    df['PSP_TIN'] = df[col_concepto].str.extract(r'(2\d{11})(?!\d)', expand=False)

    # Solo PSP_TIN válidos
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]

    # Extornos en BBVA: misma idea que BCP, usando el concepto
    duplicados = df[df.duplicated(subset=[col_nro_op], keep=False)]
    extornos = duplicados[col_concepto].str.contains('Extorno', case=False, na=False)
    numeros_extorno = duplicados[extornos][col_nro_op].unique()
    df_filtrado = df[~df[col_nro_op].isin(numeros_extorno)]

    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')
    df_filtrado = df_filtrado.rename(columns={col_nro_op: 'Nº operación'})

    return df_filtrado[['PSP_TIN', 'Monto', 'Fecha', 'Nº operación']], False


@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)


# INTERFAZ
st.title("Conciliación de Pagos - Kashio")
st.markdown("""
Detecta:
- **DSN** (Depósitos sin notificación)
- **PSD** (Pagos sin depósito)

✅ Compatible con archivos .txt y .xlsx  
✅ Compara solo hasta la **hora de corte del banco (CREP)**
""")
st.divider()

archivo_banco = st.file_uploader("📥 Subir archivo del banco (.txt o .xlsx)", type=["txt", "xlsx", "xls"])
archivo_metabase = st.file_uploader("📥 Subir archivo de Metabase (.xlsx)", type=["xlsx", "xls"])

df_banco = None
hora_corte = None
es_crep = False
banco_archivo = None  # 'BCP' o 'BBVA'


# --------------------------
# CARGA ARCHIVO DEL BANCO
# --------------------------
if archivo_banco is not None:
    start = time.time()
    try:
        if archivo_banco.name.endswith('.txt'):
            st.caption("Formato detectado: CREP (.txt)")
            df_banco, es_crep = cargar_txt_crep(archivo_banco)
            hora_corte = df_banco['FechaHora'].max()
            banco_archivo = "BCP"
            st.info(f"🕐 Hora de corte detectada: {hora_corte}")
        else:
            archivo_banco.seek(0)
            preview = pd.read_excel(archivo_banco, nrows=15, header=None)
            archivo_banco.seek(0)

            if preview.iloc[:, 0].astype(str).str.contains('Movimientos del Día', na=False).any():
                st.caption("Formato detectado: EECC BBVA (.xlsx)")
                df_banco, es_crep = cargar_excel_bbva(archivo_banco)
                banco_archivo = "BBVA"
            else:
                st.caption("Formato detectado: EECC BCP (.xlsx)")
                df_banco, es_crep = cargar_excel_bcp(archivo_banco)
                banco_archivo = "BCP"

        st.success(
            f"✅ Archivo del banco cargado con {len(df_banco)} operaciones únicas "
            f"en {round(time.time() - start, 2)} s"
        )

        # DEBUG: PSP_TIN leídos del EECC
        st.subheader("📌 PSP_TIN encontrados en el EECC")
        st.write(f"Total PSP_TIN únicos en EECC: {df_banco['PSP_TIN'].nunique()}")
        st.dataframe(df_banco)

    except Exception as e:
        st.error(f"❌ Error al procesar el archivo del banco: {e}")
        st.stop()


# --------------------------
# CRUCE CON METABASE
# --------------------------
if archivo_banco and archivo_metabase:
    start = time.time()
    df_meta = cargar_metabase(archivo_metabase)
    st.caption(f"✅ Metabase cargado en {round(time.time() - start, 2)} segundos")

    columnas = df_meta.columns.str.lower().str.strip()

    # Nuevo formato de Metabase:
    # Deuda_PspTin, Banco, " Moneda", PC_create_date_GMT_Peru
    if 'deuda_psptin' in columnas and 'banco' in columnas and 'moneda' in columnas:
        col_psptin = df_meta.columns[columnas.get_loc('deuda_psptin')]
        col_banco = df_meta.columns[columnas.get_loc('banco')]
        col_moneda = df_meta.columns[columnas.get_loc('moneda')]
        col_fecha = df_meta.columns[columnas.get_loc('pc_create_date_gmt_peru')]
    else:
        st.error("❌ No se encontraron las columnas esperadas en el archivo de Metabase.")
        st.write("Columnas encontradas:", list(df_meta.columns))
        st.stop()

    # Normalización igual a tu lógica original
    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta = df_meta.drop_duplicates(subset=col_psptin)
    df_meta[col_fecha] = pd.to_datetime(df_meta[col_fecha], errors='coerce')

    # Filtro dinámico según banco cargado (BCP o BBVA) y moneda PEN
    # Banco viene como "(BBVA) - BBVA Continental", así que usamos contains
    if hora_corte:
        df_meta_filtrado = df_meta[
            (df_meta[col_banco].astype(str).str.upper().str.contains(banco_archivo)) &
            (df_meta[col_moneda].astype(str).str.upper().str.strip() == "PEN") &
            (df_meta[col_fecha] <= hora_corte)
        ]
        st.info(
            f"🔍 {len(df_meta_filtrado)} registros filtrados de Metabase "
            f"({banco_archivo} - PEN) hasta la hora de corte"
        )
    else:
        df_meta_filtrado = df_meta[
            (df_meta[col_banco].astype(str).str.upper().str.contains(banco_archivo)) &
            (df_meta[col_moneda].astype(str).str.upper().str.strip() == "PEN")
        ]
        st.info(
            f"🔍 {len(df_meta_filtrado)} registros filtrados de Metabase "
            f"({banco_archivo} - PEN)"
        )

    # DEBUG: PSP_TIN en Metabase
    st.subheader("📌 PSP_TIN encontrados en Metabase (filtrado)")
    st.write(f"Total PSP_TIN únicos en Metabase: {df_meta_filtrado[col_psptin].nunique()}")
    st.dataframe(df_meta_filtrado[[col_psptin, col_banco, col_moneda, col_fecha]])

    # ----------------------
    # DSN y PSD (MISMA LÓGICA ORIGINAL)
    # ----------------------
    # DSN = están en el banco y no en Metabase
    dsn = df_banco[~df_banco['PSP_TIN'].isin(df_meta_filtrado[col_psptin])]
    st.subheader("🟡 DSN encontrados")
    st.write(f"{len(dsn)} DSN detectados")
    if not es_crep:
        dsn['Fecha'] = dsn['Fecha'].dt.strftime('%d/%m/%Y')
    st.dataframe(dsn)

    output_dsn = io.BytesIO()
    with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
        dsn.to_excel(writer, index=False)
    st.download_button(
        "⬇️ Descargar DSN",
        data=output_dsn.getvalue(),
        file_name="DSN_encontrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # PSD = están en Metabase y no en el banco
    psd = df_meta_filtrado[~df_meta_filtrado[col_psptin].isin(df_banco['PSP_TIN'])]
    st.subheader("🔁 PSD encontrados")
    st.write(f"{len(psd)} PSD detectados")
    st.dataframe(psd)

    output_psd = io.BytesIO()
    with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
        psd.to_excel(writer, index=False)
    st.download_button(
        "⬇️ Descargar PSD",
        data=output_psd.getvalue(),
        file_name="PSD_encontrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
