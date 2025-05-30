import streamlit as st
import pandas as pd
from datetime import datetime
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
                psp_tin_raw = linea[205:217].strip()
                psp_tin = psp_tin_raw.lstrip('0')

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
            except Exception as e:
                print(f"Error al procesar línea: {linea}\n{e}")

    return pd.DataFrame(registros)

@st.cache_data
def cargar_metabase(archivo):
    df = pd.read_excel(archivo)
    df['Deuda_PspTin'] = df['Deuda_PspTin'].astype(str)
    df = df.drop_duplicates(subset='Deuda_PspTin')
    return df

# ----------------------------
# INTERFAZ
# ----------------------------
st.title('Conciliación de Pagos: DSN y PSD')
st.markdown("""
Herramienta para identificar:
- **DSN**: Depósitos registrados en el banco que no fueron notificados en Kashio.
- **PSD**: Pagos registrados como "Pagado" en Kashio, pero no encontrados en el banco.

Esta versión usa la nueva estructura del archivo Metabase (`Deuda_PspTin`, `Banco`, `Moneda`) y elimina duplicados automáticamente.
""")
st.divider()

archivo_txt = st.file_uploader('📥 Subir archivo CREP del banco (.txt)', type=['txt'])
archivo_metabase = st.file_uploader('📥 Subir archivo de Metabase (.xlsx)', type=['xlsx', 'xls'])

if archivo_txt is not None:
    df = cargar_txt_crep(archivo_txt)
    st.caption(f"✅ EECC cargado con {len(df)} registros")
    df = df[df['PSP_TIN'].str.match(r'^2\\d{11}$', na=False)]
    df_filtrado = df.drop_duplicates(subset=['PSP_TIN'])

if archivo_txt is not None and archivo_metabase is not None:
    data_metabase = cargar_metabase(archivo_metabase)

    # Validar columnas esperadas
    columnas_requeridas = {'Deuda_PspTin', 'Banco', 'Moneda'}
    if not columnas_requeridas.issubset(set(data_metabase.columns)):
        st.error("❌ El archivo Metabase debe contener las columnas: Deuda_PspTin, Banco, Moneda")
    else:
        # Filtrar solo BCP y PEN
        data_metabase_bcp_pen = data_metabase[
            (data_metabase['Banco'].astype(str).str.upper() == 'BCP') &
            (data_metabase['Moneda'].astype(str).str.upper() == 'PEN')
        ]
        st.success(f"🔍 Filtradas {len(data_metabase_bcp_pen)} operaciones del BCP en moneda PEN (sin duplicados).")

        # -----------------------
        # 🟡 DSN
        # -----------------------
        st.subheader('🔎 DSN (Depósitos Sin Notificación)')
        dsn = df_filtrado[~df_filtrado['PSP_TIN'].isin(data_metabase_bcp_pen['Deuda_PspTin'])]
        st.write(f"✅ {len(dsn)} DSN encontrados")
        st.dataframe(dsn)

        output_dsn = io.BytesIO()
        with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
            dsn.to_excel(writer, index=False, sheet_name='DSN')
        st.download_button(
            label='Descargar DSN encontrados (Excel)',
            data=output_dsn.getvalue(),
            file_name='DSN_encontrados.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # -----------------------
        # 🔁 PSD
        # -----------------------
        st.subheader('🔁 PSD (Pagos Sin Depósito)')
        psd = data_metabase_bcp_pen[~data_metabase_bcp_pen['Deuda_PspTin'].isin(df_filtrado['PSP_TIN'])]
        st.write(f"⚠️ {len(psd)} PSD encontrados")
        st.dataframe(psd)

        output_psd = io.BytesIO()
        with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
            psd.to_excel(writer, index=False, sheet_name='PSD')
        st.download_button(
            label='Descargar PSD encontrados (Excel)',
            data=output_psd.getvalue(),
            file_name='PSD_encontrados.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
