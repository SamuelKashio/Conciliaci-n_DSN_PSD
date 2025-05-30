st.title('Conciliación de Pagos: DSN y PSD')
st.markdown("""
Este sistema identifica:
- **DSN**: Pagos que el banco recibió pero Kashio no detectó.
- **PSD**: Pagos que Kashio registró como "Pagado" pero el banco no tiene.

✅ Detecta automáticamente si el archivo de Metabase es versión **vieja o nueva**.
""")
st.divider()

archivo_txt = st.file_uploader('📥 Archivo CREP del banco (.txt)', type=['txt'])
archivo_metabase = st.file_uploader('📥 Archivo Metabase (.xlsx)', type=['xlsx', 'xls'])

if archivo_txt is not None:
    df_banco = cargar_txt_crep(archivo_txt)
    df_banco = df_banco[df_banco['PSP_TIN'].str.match(r'^2\d{11}$', na=False)]
    df_banco = df_banco.drop_duplicates(subset='PSP_TIN')
    st.success(f"✅ Cargado CREP con {len(df_banco)} operaciones únicas")

if archivo_txt is not None and archivo_metabase is not None:
    try:
        df_meta, estructura, col_psptin, col_banco, col_moneda = cargar_metabase_adaptativo(archivo_metabase)

        df_meta_filtrado = df_meta[
            (df_meta[col_banco].astype(str).str.upper() == 'BCP') &
            (df_meta[col_moneda].astype(str).str.upper() == 'PEN')
        ]
        st.info(f"📄 Estructura detectada: **{estructura.upper()}** – Filtradas {len(df_meta_filtrado)} operaciones BCP PEN")

        # -----------------------
        # 🟡 DSN
        # -----------------------
        st.subheader('🔎 DSN (Depósitos Sin Notificación)')
        dsn = df_banco[~df_banco['PSP_TIN'].isin(df_meta_filtrado[col_psptin])]
        st.write(f"✅ {len(dsn)} DSN encontrados")
        st.dataframe(dsn)

        output_dsn = io.BytesIO()
        with pd.ExcelWriter(output_dsn, engine='openpyxl') as writer:
            dsn.to_excel(writer, index=False, sheet_name='DSN')
        st.download_button("⬇️ Descargar DSN (Excel)", data=output_dsn.getvalue(), file_name="DSN_encontrados.xlsx")

        # -----------------------
        # 🔁 PSD
        # -----------------------
        st.subheader('🔁 PSD (Pagos Sin Depósito)')
        psd = df_meta_filtrado[~df_meta_filtrado[col_psptin].isin(df_banco['PSP_TIN'])]
        st.write(f"⚠️ {len(psd)} PSD encontrados")
        st.dataframe(psd)

        output_psd = io.BytesIO()
        with pd.ExcelWriter(output_psd, engine='openpyxl') as writer:
            psd.to_excel(writer, index=False, sheet_name='PSD')
        st.download_button("⬇️ Descargar PSD (Excel)", data=output_psd.getvalue(), file_name="PSD_encontrados.xlsx")

    except Exception as e:
        st.error(f"❌ Error: {e}")
