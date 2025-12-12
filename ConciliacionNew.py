import streamlit as st
import pandas as pd
import io
import time
from datetime import datetime

# =================================================
# CREP BCP (.txt)
# =================================================
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

                anio = linea[57:61]
                mes = linea[61:63]
                dia = linea[63:65]
                hora = linea[168:170]
                minuto = linea[170:172]
                segundo = linea[172:174]

                fecha_pago = f"{dia}/{mes}/{anio}"
                hora_pago = f"{hora}:{minuto}:{segundo}"
                fecha_hora_pago = datetime.strptime(
                    f"{fecha_pago} {hora_pago}", "%d/%m/%Y %H:%M:%S"
                )

                nro_operacion = linea[124:130].strip()

                registros.append({
                    "PSP_TIN": psp_tin,
                    "Monto": monto,
                    "Fecha": fecha_pago,
                    "Hora": hora_pago,
                    "FechaHora": fecha_hora_pago,
                    "Nº operación": nro_operacion
                })
            except:
                continue

    df = pd.DataFrame(registros)
    df = df[df["PSP_TIN"].str.match(r"^2\d{11}$", na=False)]
    return df.drop_duplicates(subset="PSP_TIN"), True


# =================================================
# EECC BCP (.xlsx)
# =================================================
@st.cache_data
def cargar_excel_bcp(archivo):
    df = pd.read_excel(archivo, skiprows=7)

    df["Descripción operación"] = df["Descripción operación"].astype(str).str.strip()
    df["Nº operación"] = df["Nº operación"].astype(str).str.strip()
    df["Monto"] = pd.to_numeric(df["Monto"], errors="coerce")
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    df["PSP_TIN"] = df["Descripción operación"].str.extract(r"(2\d{11})(?!\d)")

    duplicados = df[df.duplicated(subset=["Nº operación"], keep=False)]
    extornos = duplicados["Descripción operación"].str.contains("Extorno", case=False, na=False)
    numeros_extorno = duplicados[extornos]["Nº operación"].unique()

    df = df[~df["Nº operación"].isin(numeros_extorno)]
    df = df[df["PSP_TIN"].str.match(r"^2\d{11}$", na=False)]
    df = df.drop_duplicates(subset="PSP_TIN")

    return df[["PSP_TIN", "Monto", "Fecha", "Nº operación"]], False


# =================================================
# EECC BBVA (.xlsx)
# =================================================
@st.cache_data
def cargar_excel_bbva(archivo):
    df = pd.read_excel(archivo, skiprows=10)
    df.columns = df.columns.str.strip()

    df["Monto"] = pd.to_numeric(df["Importe"], errors="coerce")
    df["Fecha"] = pd.to_datetime(df["F.Operación"], format="%d-%m-%Y", errors="coerce")

    df["Concepto"] = df["Concepto"].astype(str).str.strip()
    df["PSP_TIN"] = df["Concepto"].str.extract(r"(2\d{11})(?!\d)")

    df = df[df["PSP_TIN"].str.match(r"^2\d{11}$", na=False)]

    duplicados = df[df.duplicated(subset=["Núm.Movimiento"], keep=False)]
    extornos = duplicados["Concepto"].str.contains("Extorno", case=False, na=False)
    numeros_extorno = duplicados[extornos]["Núm.Movimiento"].unique()

    df = df[~df["Núm.Movimiento"].isin(numeros_extorno)]
    df = df.drop_duplicates(subset="PSP_TIN")

    df = df.rename(columns={"Núm.Movimiento": "Nº operación"})
    return df[["PSP_TIN", "Monto", "Fecha", "Nº operación"]], False


# =================================================
# METABASE
# =================================================
@st.cache_data
def cargar_metabase(archivo):
    return pd.read_excel(archivo)


# =================================================
# INTERFAZ
# =================================================
st.title("Conciliación de Pagos - Kashio")
st.divider()

archivo_banco = st.file_uploader("📥 Subir EECC del banco", type=["txt", "xlsx", "xls"])
archivo_metabase = st.file_uploader("📥 Subir archivo de Metabase", type=["xlsx", "xls"])

df_banco = None
hora_corte = None
es_crep = False
banco_archivo = None


# =================================================
# CARGA BANCO
# =================================================
if archivo_banco:
    start = time.time()

    if archivo_banco.name.endswith(".txt"):
        df_banco, es_crep = cargar_txt_crep(archivo_banco)
        hora_corte = df_banco["FechaHora"].max()
        banco_archivo = "BCP"
        st.info(f"Hora de corte: {hora_corte}")
    else:
        archivo_banco.seek(0)
        preview = pd.read_excel(archivo_banco, nrows=15, header=None)
        archivo_banco.seek(0)

        if preview.iloc[:, 0].astype(str).str.contains("Movimientos del Día", na=False).any():
            df_banco, es_crep = cargar_excel_bbva(archivo_banco)
            banco_archivo = "BBVA"
        else:
            df_banco, es_crep = cargar_excel_bcp(archivo_banco)
            banco_archivo = "BCP"

    st.success(f"EECC cargado con {len(df_banco)} PSP_TIN únicos")
    st.dataframe(df_banco)


# =================================================
# CRUCE
# =================================================
if archivo_banco and archivo_metabase:
    df_meta = cargar_metabase(archivo_metabase)

    col_psptin = "Deuda_PspTin"
    col_banco = "Banco"
    col_moneda = " Moneda"
    col_fecha = "PC_create_date_GMT_Peru"

    df_meta[col_psptin] = df_meta[col_psptin].astype(str)
    df_meta = df_meta.drop_duplicates(subset=col_psptin)
    df_meta[col_fecha] = pd.to_datetime(df_meta[col_fecha], errors="coerce")

    df_meta_filtrado = df_meta[
        (df_meta[col_banco].astype(str).str.upper().str.contains(banco_archivo)) &
        (df_meta[col_moneda].astype(str).str.upper().str.strip() == "PEN")
    ]

    st.info(f"PSP_TIN únicos en Metabase: {df_meta_filtrado[col_psptin].nunique()}")

    # DSN
    dsn = df_banco[~df_banco["PSP_TIN"].isin(df_meta_filtrado[col_psptin])]
    st.subheader("🟡 DSN encontrados")
    st.write(len(dsn))
    st.dataframe(dsn)

    # XLSX DSN
    out_dsn = io.BytesIO()
    with pd.ExcelWriter(out_dsn, engine="openpyxl") as writer:
        dsn.to_excel(writer, index=False)

    st.download_button(
        "⬇️ Descargar DSN (Excel)",
        out_dsn.getvalue(),
        "DSN_encontrados.xlsx"
    )

    # ===============================
    # NUEVO: TXT CON PSP_TIN
    # ===============================
    psptin_txt = ",".join(
        dsn["PSP_TIN"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    st.download_button(
        "⬇️ Descargar DSN (PSP_TIN en .txt)",
        data=psptin_txt.encode("utf-8"),
        file_name="DSN_psptin.txt",
        mime="text/plain"
    )

    # PSD
    psd = df_meta_filtrado[~df_meta_filtrado[col_psptin].isin(df_banco["PSP_TIN"])]
    st.subheader("🔁 PSD encontrados")
    st.write(len(psd))
    st.dataframe(psd)
