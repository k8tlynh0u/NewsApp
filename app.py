# ==============================================================================
#      NEWS MENTION, SUMMARY & SENTIMENT ANALYZER (V-FINAL - DIAGNOSTIC)
#
# This special version is designed to print the raw HTML from Google's
# redirect page so we can see exactly why it's failing to resolve.
# ==============================================================================

import streamlit as st
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import re

import feedparser
import requests
import spacy
from newsapi.newsapi_client import NewsApiClient
from newspaper import Article, Config
from openai import OpenAI

# --- SETUP & CONFIGURATION ---

@st.cache_resource
def setup_openai_client():
    try:
        return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    except Exception as e:
        st.error(f"Could not set up OpenAI client: {e}"); st.stop()

@st.cache_resource
def setup_spacy_model():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        st.error("SpaCy model 'en_core_web_sm' not found in requirements.txt."); st.stop()

openai_client = setup_openai_client()
nlp = setup_spacy_model()

MY_API_KEY = st.secrets["NEWSAPI_KEY"]
SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
SENDER_PASSWORD = st.secrets["SENDER_PASSWORD"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- HELPER FUNCTIONS ---

def fetch_from_google_rss(person_name, from_date, to_date):
    try:
        query_terms = f'"{person_name}" after:{from_date.strftime("%Y-%m-%d")} before:{to_date.strftime("%Y-%m-%d")}'
        rss_url = f"https://news.google.com/rss/search?q={query_terms.replace(' ', '%20')}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        return [entry.get("link", "") for entry in feed.entries]
    except Exception as e:
        st.warning(f"Could not fetch from Google News RSS: {e}"); return []

def fetch_from_newsapi(api_client, person_name, from_date, to_date):
    try:
        all_articles = api_client.get_everything(
            q=f'"{person_name}"', from_param=from_date.isoformat(), to=to_date.isoformat(),
            language='en', sort_by='relevancy', page_size=40
        )
        return [article['url'] for article in all_articles.get('articles', [])]
    except Exception as e:
        st.warning(f"Could not fetch from NewsAPI: {e}"); return []

# THIS IS THE SPECIAL DIAGNOSTIC FUNCTION
def diagnostic_resolve_google_news_url(google_url: str, session) -> None:
    """
    This function will fetch the Google News page and PRINT its contents
    to the Streamlit app screen for debugging purposes.
    """
    try:
        response = session.get(google_url, timeout=15)
        response.raise_for_status()
        
        # Print the first 1000 characters of the page content
        st.info(f"--- DEBUG: Content from {google_url} ---")
        st.code(response.text[:1000]) # Use st.code to preserve formatting
        st.info("--- END DEBUG ---")

    except requests.RequestException as e:
        st.error(f"Request failed for {google_url}: {e}")
    
    # This function doesn't return anything useful, it just prints.
    return None

# --- STREAMLIT WEB APPLICATION INTERFACE ---
st.set_page_config(page_title="News Analyzer - DIAGNOSTIC MODE", layout="wide", page_icon="🔬")
st.title("🔬 News Analyzer - DIAGNOSTIC MODE")
st.warning("This is a special diagnostic version. It will not analyze articles. Please run a search and copy the entire output for the support person.")

person_name = st.text_input("👤 **Person's Full Name**", placeholder="e.g., Joe Biden")
date_input = st.date_input("🗓️ **Date to Search**", datetime.now() - timedelta(days=2))

if st.button("🚀 Run Diagnostic Test", type="primary", use_container_width=True):
    if not person_name:
        st.warning("Please enter a person's name to start the test."); st.stop()

    from_date = date_input
    to_date = from_date + timedelta(days=1)
    
    with st.spinner(f"🔍 Fetching Google News links for '{person_name}'..."):
        google_urls = fetch_from_google_rss(person_name, from_date, to_date)
    
    if not google_urls:
        st.error("Could not find any Google News links to test."); st.stop()

    st.success(f"Found {len(google_urls)} links. Now attempting to see their content...")
    st.markdown("---")
    
    with requests.Session() as session:
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'})
        for url in google_urls:
            diagnostic_resolve_google_news_url(url, session)

    st.success("✅ Diagnostic Test Complete. Please copy all the text from this page and send it back.")
