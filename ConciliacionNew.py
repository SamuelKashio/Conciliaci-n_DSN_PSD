import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

# -------------------------------------------------
# CARGA CREP TXT (BCP)
# -------------------------------------------------
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


# -------------------------------------------------
# CARGA EECC BCP EXCEL
# -------------------------------------------------
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


# -------------------------------------------------
# CARGA EECC BBVA EXCEL
# -------------------------------------------------
@st.cache_data
def cargar_excel_bbva(archivo):
    df = pd.read_excel(archivo, skiprows=10)
    cols = df.columns

    col_concepto = 'Concepto' if 'Concepto' in cols else cols[3]

    if 'Nº Operación' in cols:
        col_nro_op = 'Nº Operación'
    elif 'N° Operación' in cols:
        col_nro_op = 'N° Operación'
    else:
        col_nro_op = cols[4]

    col_importe = 'Importe' if 'Importe' in cols else cols[5]
    col_fecha = 'F.Operación' if 'F.Operación' in cols else cols[0]

    df[col_concepto] = df[col_concepto].astype(str).str.strip()
    df[col_nro_op] = df[col_nro_op].astype(str).str.strip()

    df['Monto'] = pd.to_numeric(df[col_importe], errors='coerce')
    df['Fecha'] = pd.to_datetime(df[col_fecha], format='%d-%m-%Y', errors='coerce')

    df['PSP_TIN'] = df[col_concepto].str.extract(r'(2\d{11})(?!\d)', expand=False)
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]

    duplicados = df[df.duplicated(subset=[col_nro_op], keep=False)]
    ops_extorno = duplicados.groupby(col_nro_op)['Monto'].apply(
        lambda s: s.gt(0).any() and s.lt(0).any()
    )
    numeros_extorno = ops_extorno[ops_extorno].index

    df_filtrado = df[~df[col_nro_op].isin(numeros_extorno)]
    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')

    df_filtrado = df_filtrado.rename(columns={col_nro_op: 'Nº operación'})
    return df_filtrado[['PSP_TIN', 'Monto', 'Fecha', 'Nº operación']], False


# -------------------------------------------------
# CARGA METABASE
# -------------------------------------------------
@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)


# -------------------------------------------------
# INTERFAZ STREAMLIT
# -------------------------------------------------
st.title("Conciliación de Pagos - Kashio")
st.markdown("""
Detecta:
- **DSN** (Depósitos sin notificación)
- **PSD** (Pagos sin depósito)

✅ Compatible con archivos .txt y .xlsx  
""")
st.divider()

archivo_banco = st.file_uploader("📥 Subir archivo del banco (.txt o .xlsx)", type=["txt", "xlsx", "xls"])
archivo_metabase = st.file_uploader("📥 Subir archivo de Metabase (.xlsx)", type=["xlsx", "xls"])

df_banco = None
hora_corte = None
es_crep = False
banco_archivo = None


# -------------------------------------------------
# PROCESO DE CARGA ARCHIVO BANCO
# -------------------------------------------------
if archivo_banco is not None:
    start = time.time()
    try:
        if archivo_banco.name.endswith('.txt'):
            st.caption("Formato detectado: CREP (.txt)")
            df_banco, es_crep = cargar_txt_crep(archivo_banco)
            hora_corte = df_banco['FechaHora'].max()
            banco_archivo = "BCP"
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
            f"Archivo del banco cargado con {len(df_banco)} operaciones únicas "
            f"en {round(time.time() - start, 2)} s"
        )

    except Exception as e:
        st.error(f"Error al procesar el archivo del banco: {e}")
        st.stop()


# -------------------------------------------------
# CRUCE CON METABASE
# -------------------------------------------------
if archivo_banco and archivo_metabase:
    start = time.time()
    df_meta = cargar_metabase(archivo_metabase)

    columnas_norm = df_meta.columns.str.lower().str.strip()

    mapa_columnas = {
        "psptin": ["deuda_psptin"],
        "banco": ["banco"],
        "moneda": ["moneda", " moneda"],
        "fecha": ["pc_create_date_gmt_peru"]
    }

    def encontrar(nombres):
        for name in nombres:
            if name in columnas_norm:
                return df_meta.columns[columnas_norm.get_loc(name)]
        return None

    col_psptin = encontrar(mapa_columnas["psptin"])
    col_banco = encontrar(mapa_columnas["banco"])
    col_moneda = encontrar(mapa_columnas["moneda"])
    col_fecha = encontrar(mapa_columnas["fecha"])

    if not all([col_psptin, col_banco, col_moneda, col_fecha]):
        st.error("❌ No se encontraron las columnas necesarias en Metabase.")
        st.write(list(df_meta.columns))
        st.stop()

    # Normalizar PSP_TIN de Metabase
    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta["PSP_TIN_META"] = df_meta[col_psptin].str.extract(r'(2\d{11})(?!\d)', expand=False)
    df_meta = df_meta[df_meta["PSP_TIN_META"].notna()]
    df_meta = df_meta.drop_duplicates(subset="PSP_TIN_META")

    df_meta[col_fecha] = pd.to_datetime(df_meta[col_fecha], errors='coerce')

    # Filtrar Metabase según banco y moneda PEN
    df_meta_filtrado = df_meta[
        (df_meta[col_banco].astype(str).str.upper().str.contains(banco_archivo)) &
        (df_meta[col_moneda].astype(str).str.upper().str.strip() == "PEN")
    ]

    # ----------------------
    # CÁLCULO DE DSN Y PSD
    # ----------------------

    # DSN → Están en banco pero NO en Metabase
    dsn = df_banco[~df_banco["PSP_TIN"].isin(df_meta_filtrado["PSP_TIN_META"])]

    st.subheader("🟡 DSN encontrados")
    st.write(len(dsn))
    st.dataframe(dsn)

    # Exportar DSN
    out_dsn = io.BytesIO()
    with pd.ExcelWriter(out_dsn, engine="openpyxl") as writer:
        dsn.to_excel(writer, index=False)
    st.download_button("⬇ Descargar DSN", out_dsn.getvalue(), "DSN.xlsx")

    # PSD → Están en Metabase pero NO en banco
    psd = df_meta_filtrado[~df_meta_filtrado["PSP_TIN_META"].isin(df_banco["PSP_TIN"])]

    st.subheader("🔁 PSD encontrados")
    st.write(len(psd))
    st.dataframe(psd)

    # Exportar PSD
    out_psd = io.BytesIO()
    with pd.ExcelWriter(out_psd, engine="openpyxl") as writer:
        psd.to_excel(writer, index=False)
    st.download_button("⬇ Descargar PSD", out_psd.getvalue(), "PSD.xlsx")
