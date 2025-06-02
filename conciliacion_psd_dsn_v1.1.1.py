import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

# --------------------------
# CARGA ARCHIVOS
# --------------------------
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
                fecha_hora_pago = datetime.strptime(f"{dia}/{mes}/{anio} {hora}:{minuto}:{segundo}", "%d/%m/%Y %H:%M:%S")
                nro_operacion = linea[124:130].strip()
                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto total pagado': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha de pago': fecha_pago,
                    'Hora de atención': hora_pago,
                    'FechaHora': fecha_hora_pago,
                    'Nº operación': nro_operacion
                })
            except:
                continue
    df = pd.DataFrame(registros)
    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    return df.drop_duplicates(subset='PSP_TIN')

@st.cache_data
def cargar_excel_bcp(archivo):
    df_preview = pd.read_excel(archivo, nrows=5)
    if 'Descripción operación' in df_preview.columns:
        df = pd.read_excel(archivo, skiprows=7)
        col_desc = 'Descripción operación'
        col_fecha = 'Fecha'
        col_hora = 'Hora'
        col_nro_op = 'Nº operación'
    else:
        df = pd.read_excel(archivo, skiprows=10)
        df.columns = df.iloc[0]
        df = df[1:]
        df = df.rename(columns=lambda x: str(x).strip())
        col_desc = 'Descripción'
        col_fecha = 'Fecha'
        col_hora = 'Operación - Hora'
        col_nro_op = 'Número de Operación'

    df[col_desc] = df[col_desc].astype(str).str.strip()
    df[col_nro_op] = df[col_nro_op].astype(str).str.strip()
    df['PSP_TIN'] = df[col_desc].str.extract(r'(2\d{11})(?!\d)', expand=False)
    df['FechaHora'] = pd.to_datetime(df[col_fecha].astype(str) + ' ' + df[col_hora].astype(str), errors='coerce')
    duplicados = df[df.duplicated(subset=[col_nro_op], keep=False)]
    extornos = duplicados[col_desc].str.contains('Extorno', case=False, na=False)
    numeros_extorno = duplicados[extornos][col_nro_op].unique()
    df_filtrado = df[~df[col_nro_op].isin(numeros_extorno)]
    df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')
    df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    return df_filtrado[['PSP_TIN', 'FechaHora']]

@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)

# --------------------------
# INTERFAZ
# --------------------------
st.title("Conciliación de Pagos - Kashio")
st.markdown("""
Detecta:
- **DSN** (Depósitos sin notificación)
- **PSD** (Pagos sin depósito)

✅ Compatible con archivos .txt y .xlsx  
✅ Compara solo hasta la **hora de corte del banco**
""")
st.divider()

archivo_banco = st.file_uploader("📥 Subir archivo del banco (.txt o .xlsx)", type=["txt", "xlsx", "xls"])
archivo_metabase = st.file_uploader("📥 Subir archivo de Metabase (.xlsx)", type=["xlsx", "xls"])

df_banco = None
hora_corte = None

if archivo_banco is not None:
    start = time.time()
    try:
        if archivo_banco.name.endswith('.txt'):
            st.caption("Formato detectado: CREP (.txt)")
            df_banco = cargar_txt_crep(archivo_banco)
        else:
            st.caption("Formato detectado: EECC BCP (.xlsx)")
            df_banco = cargar_excel_bcp(archivo_banco)
        hora_corte = df_banco['FechaHora'].max()
        st.success(f"✅ EECC del banco cargado con {len(df_banco)} operaciones únicas en {round(time.time() - start, 2)} s")
        st.info(f"🕐 Hora de corte detectada: {hora_corte}")
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo del banco: {e}")
        st.stop()

if archivo_banco and archivo_metabase:
    start = time.time()
    df_meta = cargar_metabase(archivo_metabase)
    st.caption(f"✅ Metabase cargado en {round(time.time() - start, 2)} segundos")

    columnas = df_meta.columns.str.lower()
    if 'deuda_psptin' in columnas and 'banco' in columnas and 'moneda' in columnas:
        col_psptin = df_meta.columns[columnas.get_loc('deuda_psptin')]
        col_banco = df_meta.columns[columnas.get_loc('banco')]
        col_moneda = df_meta.columns[columnas.get_loc('moneda')]
        col_fecha = df_meta.columns[columnas.get_loc('pc_create_date_gmt_peru')]
    else:
        col_psptin = df_meta.columns[26]
        col_banco = df_meta.columns[10]
        col_moneda = df_meta.columns[21]
        col_fecha = df_meta.columns[15]

    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta = df_meta.drop_duplicates(subset=col_psptin)
    df_meta[col_fecha] = pd.to_datetime(df_meta[col_fecha], errors='coerce')

    df_meta_bcp_pen = df_meta[
        (df_meta[col_banco].astype(str).str.upper() == "BCP") &
        (df_meta[col_moneda].astype(str).str.upper() == "PEN") &
        (df_meta[col_fecha] <= hora_corte)
    ]
    st.info(f"🔍 {len(df_meta_bcp_pen)} registros filtrados de Metabase (BCP - PEN) hasta la hora de corte")

    # DSN
    dsn = df_banco[~df_banco['PSP_TIN'].isin(df_meta_bcp_pen[col_psptin])]
    st.subheader("🟡 DSN encontrados")
    st.write(f"{len(dsn)} DSN detectados")
    st.dataframe(dsn)
    output_dsn = io.BytesIO()
    with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
        dsn.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar DSN", data=output_dsn.getvalue(),
                       file_name="DSN_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # PSD
    psd = df_meta_bcp_pen[~df_meta_bcp_pen[col_psptin].isin(df_banco['PSP_TIN'])]
    st.subheader("🔁 PSD encontrados")
    st.write(f"{len(psd)} PSD detectados")
    st.dataframe(psd)
    output_psd = io.BytesIO()
    with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
        psd.to_excel(writer, index=False)
    st.download_button("⬇️ Descargar PSD", data=output_psd.getvalue(),
                       file_name="PSD_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
