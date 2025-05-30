import streamlit as st
import pandas as pd
import time
import io

# ----------------------------
# FUNCIONES
# ----------------------------
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
                fecha_pago = f"{dia}/{mes}/{anio}" if anio and mes and dia else ""

                hora = linea[168:170]
                minuto = linea[170:172]
                segundo = linea[172:174]
                hora_pago = f"{hora}:{minuto}:{segundo}" if hora and minuto and segundo else ""

                nro_operacion = linea[124:130].strip()

                registros.append({
                    'PSP_TIN': psp_tin,
                    'Monto total pagado': monto,
                    'Medio de atención': medio_atencion,
                    'Fecha de pago': fecha_pago,
                    'Hora de atención': hora_pago,
                    'Nº operación': nro_operacion
                })
            except:
                continue

    return pd.DataFrame(registros)

@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)

# ----------------------------
# INTERFAZ
# ----------------------------
st.title('Conciliación de Pagos: DSN y PSD')
st.markdown("""
Herramienta para identificar:

- **DSN**: Depósitos registrados en el banco pero no notificados en Kashio.
- **PSD**: Pagos registrados en Kashio como "Pagado", pero no encontrados en el banco.

✅ Compatible con estructura antigua y nueva del archivo de Metabase.
""")
st.divider()

archivo_txt = st.file_uploader('📥 Subir archivo CREP del banco (.txt)', type=['txt'])
archivo_metabase = st.file_uploader('📥 Subir archivo de Metabase (.xlsx)', type=['xlsx', 'xls'])

if archivo_txt:
    start = time.time()
    df_banco = cargar_txt_crep(archivo_txt)
    st.caption(f"✅ EECC del banco cargado en {round(time.time() - start, 2)} segundos")

    df = df[df['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    df_banco = df_banco.drop_duplicates(subset='PSP_TIN')
    st.dataframe(df_banco.head())

if archivo_txt and archivo_metabase:
    start = time.time()
    df_meta = cargar_metabase(archivo_metabase)
    st.caption(f"✅ Metabase cargado en {round(time.time() - start, 2)} segundos")

    columnas = df_meta.columns.str.lower()
    if 'deuda_psptin' in columnas and 'banco' in columnas and 'moneda' in columnas:
        st.success("📄 Formato de Metabase: NUEVO")
        col_psptin = df_meta.columns[columnas.get_loc('deuda_psptin')]
        col_banco = df_meta.columns[columnas.get_loc('banco')]
        col_moneda = df_meta.columns[columnas.get_loc('moneda')]
    else:
        st.success("📄 Formato de Metabase: ANTIGUO")
        if len(df_meta.columns) < 27:
            st.error("❌ Archivo de Metabase no válido: faltan columnas necesarias.")
            st.stop()
        col_psptin = df_meta.columns[26]
        col_banco = df_meta.columns[10]
        col_moneda = df_meta.columns[21]

    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta = df_meta.drop_duplicates(subset=col_psptin)

    df_meta_filtrado = df_meta[
        (df_meta[col_banco].astype(str).str.upper() == 'BCP') &
        (df_meta[col_moneda].astype(str).str.upper() == 'PEN')
    ]
    st.info(f"🔍 Se filtraron {len(df_meta_filtrado)} registros BCP PEN únicos de Metabase.")

    # Conciliación
    dsn = df_banco[~df_banco['PSP_TIN'].isin(df_meta_filtrado[col_psptin])]
    psd = df_meta_filtrado[~df_meta_filtrado[col_psptin].isin(df_banco['PSP_TIN'])]

    # ------------------ DSN ------------------
    st.subheader('🔎 DSN (Depósitos Sin Notificación)')
    st.write(f"🟡 {len(dsn)} DSN encontrados")
    st.dataframe(dsn)
    output_dsn = io.BytesIO()
    with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
        dsn.to_excel(writer, index=False, sheet_name='DSN')
    st.download_button("⬇️ Descargar DSN", data=output_dsn.getvalue(),
                       file_name="DSN_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ------------------ PSD ------------------
    st.subheader('🔁 PSD (Pagos Sin Depósito)')
    st.write(f"⚠️ {len(psd)} PSD encontrados")
    st.dataframe(psd)
    output_psd = io.BytesIO()
    with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
        psd.to_excel(writer, index=False, sheet_name='PSD')
    st.download_button("⬇️ Descargar PSD", data=output_psd.getvalue(),
                       file_name="PSD_encontrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
