import streamlit as st
import pandas as pd

st.title("🏞️ Land Portfolio Analyzer")
st.write("Hello World - App is working!")

uploaded_file = st.file_uploader("Upload CSV", type=['csv'])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.write(f"Loaded {len(df)} rows")
    st.dataframe(df.head())
else:
    st.write("Please upload a CSV file")
