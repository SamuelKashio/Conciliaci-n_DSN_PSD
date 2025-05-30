data_metabase = cargar_metabase(archivo_metabase)
st.caption(f"⏱ Metabase cargado en {round(time.time() - start, 2)} segundos")

data_metabase['psp_tin'] = data_metabase['psp_tin'].astype(str)
data_metabase = data_metabase.drop_duplicates(subset='psp_tin')  # 👈 ELIMINAR DUPLICADOS

if 10 >= len(data_metabase.columns) or 21 >= len(data_metabase.columns):
    st.error("❌ No se encontraron las columnas 11 (banco) y 22 (moneda) en el archivo de Metabase.")
else:
    col_banco = data_metabase.columns[10]
    col_moneda = data_metabase.columns[21]
