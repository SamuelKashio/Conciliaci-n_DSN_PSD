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
def cargar_excel_banco(archivo):
    try:
        df_preview = pd.read_excel(archivo, nrows=15).fillna('')
        columnas = df_preview.columns.str.lower()

        if 'operación - hora' in columnas:
            st.caption("Formato detectado: BCP - Movimientos Históricos")
            df = pd.read_excel(archivo, skiprows=4)
            desc, fecha, hora, nro_op = 'Descripción', 'Fecha', 'Operación - Hora', 'Número de Operación'

        elif 'descripción operación' in columnas:
            st.caption("Formato detectado: BCP - Movimientos Diarios")
            df = pd.read_excel(archivo, skiprows=7)
            desc, fecha, hora, nro_op = 'Descripción operación', 'Fecha operación', 'Hora', 'Nº operación'

        elif 'descripción' in columnas and 'nro. de operación' in columnas:
            st.caption("Formato detectado: INTERBANK")
            df = pd.read_excel(archivo, skiprows=11)
            desc, fecha, hora, nro_op = 'Descripción', 'Fecha de operación', None, 'Nro. de operación'
        else:
            raise ValueError("Formato de archivo no reconocido")

        df[desc] = df[desc].astype(str).str.strip()
        df[nro_op] = df[nro_op].astype(str).str.strip()
        df['PSP_TIN'] = df[desc].str.extract(r'(2\d{11})(?!\d)', expand=False)

        if hora:
            df['FechaHora'] = pd.to_datetime(df[fecha].astype(str) + ' ' + df[hora].astype(str), errors='coerce')
        else:
            df['FechaHora'] = pd.to_datetime(df[fecha], errors='coerce')

        duplicados = df[df.duplicated(subset=[nro_op], keep=False)]
        extornos = duplicados[desc].str.contains('Extorno', case=False, na=False)
        numeros_extorno = duplicados[extornos][nro_op].unique()
        df_filtrado = df[~df[nro_op].isin(numeros_extorno)]
        df_filtrado = df_filtrado.drop_duplicates(subset='PSP_TIN')
        df_filtrado = df_filtrado[df_filtrado['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
        return df_filtrado[['PSP_TIN', 'FechaHora']]

    except Exception as e:
        raise ValueError(f"Error al procesar archivo Excel del banco: {e}")

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

✅ Compatible con BCP, INTERBANK y CREP (.txt)  
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
            df_banco = cargar_excel_banco(archivo_banco)

        hora_corte = df_banco['FechaHora'].max()
        st.success(f"✅ Archivo del banco cargado con {len(df_banco)} operaciones únicas en {round(time.time() - start, 2)} s")
        st.info(f"🕐 Hora de corte detectada: {hora_corte}")
    except Exception as e:
        st.error(f"❌ {e}")
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
        (df_meta[col_banco].astype(str).str.upper().isin(["BCP", "INTERBANK"])) &
        (df_meta[col_moneda].astype(str).str.upper() == "PEN") &
        (df_meta[col_fecha] <= hora_corte)
    ]
    st.info(f"🔍 {len(df_meta_bcp_pen)} registros filtrados de Metabase (BCP / INTERBANK - PEN) hasta la hora de corte")

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
