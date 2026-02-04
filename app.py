import streamlit as st
from google import genai
from google.genai import types
import pandas as pd
import json
import os
import tempfile
from io import BytesIO

# --- APP CONFIGURATION ---
MODEL_ID = "gemini-3-flash-preview"  # Using the specific 3.0 Flash Preview model
APP_TITLE = "Anant: Stockist & Invoice Extractor"

st.set_page_config(page_title=APP_TITLE, page_icon="📄")

# --- SIDEBAR & API SETUP ---
st.sidebar.title("⚙️ Configuration")
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("🔑 API Key not found! Please set it in Streamlit Secrets.")
    st.stop()

client = genai.Client(api_key=api_key)

# --- MAIN UI ---
st.title(f"🚀 {APP_TITLE}")
st.write(f"Powered by **{MODEL_ID}**")
st.markdown("Upload an Invoice (Image or PDF) to extract: **Stockist, Retailer, Invoice Info, Products, and Discounts**.")

uploaded_file = st.file_uploader("Choose a file...", type=["jpg", "jpeg", "png", "pdf"])

if uploaded_file is not None:
    # Save uploaded file to a temporary path (Required for Gemini File API)
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_file_path = tmp_file.name

    st.info("Analyzing document... this may take a moment.")

    try:
        # 1. Upload file to Gemini
        # For PDFs, we upload to the File API. For images, we can do the same for consistency.
        sample_file = client.files.upload(path=tmp_file_path)

        # 2. Define the extraction schema (Structured Output)
        # We tell Gemini exactly what JSON structure we want
        prompt = """
        Extract the following information from this invoice document:
        1. Stockist Name
        2. Retailer Name
        3. Invoice Number
        4. Invoice Date
        5. Total Discount Amount (if any)
        6. A list of all Products, including Product Name, Quantity, Rate, and Net Amount.

        Return the data in valid JSON format.
        """

        # 3. Call Gemini 3.0 Flash
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[sample_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        # 4. Parse the JSON response
        data = json.loads(response.text)

        # Display Summary Data
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🏢 Entities")
            st.text_input("Stockist", data.get("stockist_name", "N/A"))
            st.text_input("Retailer", data.get("retailer_name", "N/A"))
        with col2:
            st.subheader("🧾 Invoice Details")
            st.text_input("Invoice #", data.get("invoice_number", "N/A"))
            st.text_input("Date", data.get("invoice_date", "N/A"))
            st.text_input("Total Discount", data.get("total_discount_amount", "0"))

        # Process Products into a DataFrame
        products = data.get("products", [])
        if products:
            st.subheader("📦 Product Details")
            df = pd.DataFrame(products)
            st.dataframe(df)

            # --- EXPORT TO EXCEL ---
            # We create an in-memory Excel file for download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Products')
                # Add a metadata sheet for the other info
                meta_df = pd.DataFrame([{
                    "Stockist": data.get("stockist_name"),
                    "Retailer": data.get("retailer_name"),
                    "Invoice No": data.get("invoice_number"),
                    "Date": data.get("invoice_date")
                }])
                meta_df.to_excel(writer, index=False, sheet_name='Invoice Info')
            
            output.seek(0)
            
            st.download_button(
                label="📥 Download Extracted Data as Excel",
                data=output,
                file_name=f"Anant_{data.get('invoice_number', 'data')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No product line items were detected.")

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    
    finally:
        # Cleanup: Remove temp file
        os.unlink(tmp_file_path)
