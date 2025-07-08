# ==============================================================================
#      NEWS MENTION, SUMMARY & SENTIMENT ANALYZER (V7 - NO SELENIUM)
#
# This version removes Selenium entirely to ensure stability on Streamlit Cloud.
# It now relies exclusively on NewsAPI, which is more reliable for deployment.
# ==============================================================================

# --- STEP 1: IMPORT ALL TOOLS ---
import streamlit as st
import os
import smtplib
from datetime import datetime, timedelta
from urllib.parse import quote
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import spacy
from newsapi.newsapi_client import NewsApiClient
from newspaper import Article, Config
from openai import OpenAI

# --- STEP 2: SETUP & CONFIGURATION ---

@st.cache_resource
def setup_openai_client():
    try:
        openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        return openai_client
    except Exception as e:
        st.error(f"Could not set up OpenAI client: {e}")
        st.stop()

@st.cache_resource
def setup_spacy_model():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        st.error("SpaCy model 'en_core_web_sm' not found. Please ensure it's in your requirements.txt.")
        st.stop()

# --- Load all necessary models and clients ---
openai_client = setup_openai_client()
nlp = setup_spacy_model()

# --- API & Email Configuration ---
MY_API_KEY = st.secrets["NEWSAPI_KEY"]
SENDER_EMAIL = st.secrets["SENDER_EMAIL"]
SENDER_PASSWORD = st.secrets["SENDER_PASSWORD"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# --- STEP 3: HELPER FUNCTIONS ---

def fetch_from_newsapi(api_client, person_name, from_date, to_date):
    urls_found = []
    try:
        all_articles = api_client.get_everything(
            q=f'"{person_name}"',
            from_param=from_date.isoformat(),
            to=to_date.isoformat(),
            language='en',
            sort_by='relevancy',
            page_size=20  # Get a decent number of articles
        )
        for article in all_articles.get('articles', []):
            urls_found.append(article['url'])
        return urls_found
    except Exception as e:
        st.error(f"Error fetching from NewsAPI: {e}")
        return []

def process_article(url, name_to_find):
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        config.request_timeout = 25
        
        article = Article(url, config=config)
        article.download()
        article.parse()

        title = article.title if article.title else "Title Not Found"
        
        if not article.text or len(article.text) < 200:
            st.warning(f"-> Could not extract meaningful text from: {url}")
            return (None, None, None)
        
        full_text = article.text
        doc = nlp(full_text)
        found_sentences = [s.text.strip().replace('\n', ' ') for s in doc.sents if name_to_find.lower() in s.text.lower()]
        return (title, found_sentences, full_text)
    except Exception as e:
        st.warning(f"-> Could not process article at {url}. Reason: {e}")
        return (None, None, None)

# (GPT and Email functions remain the same)
def get_summary_from_gpt(article_text):
    if not article_text: return "Article text was empty; summary could not be generated."
    system_prompt = "You are an expert news editor. Create a concise, neutral, two-sentence summary of the provided news article text."
    user_prompt = f"Please summarize the following article text:\n\n---\n\n{article_text}"
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2, max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Summary generation failed: {e}"

def get_sentiment_from_gpt(person_name, sentences):
    if not sentences: return "No mentions found; sentiment not analyzed."
    context_text = " ".join(sentences)
    system_prompt = "You are an expert news analyst. Determine if the sentiment of a news mention towards a person is Positive, Negative, or Neutral. Base your judgment ONLY on the provided text."
    user_prompt = f"Person: {person_name}\nSentences: \"{context_text}\"\n\nFormat your response as: Sentiment: [Positive/Negative/Neutral]. Justification: [A brief, one-sentence explanation.]"
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0, max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e: return f"Sentiment analysis failed: {e}"

def send_email_with_attachment(subject, body, recipient_email, file_path):
    if not SENDER_PASSWORD:
        st.error("Email password not found in Streamlit secrets. Cannot send email.")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        with open(file_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename= {os.path.basename(file_path)}')
        msg.attach(part)
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"An error occurred while sending the email: {e}")
        return False


# --- STEP 4: STREAMLIT WEB APPLICATION INTERFACE ---

st.set_page_config(page_title="News & Sentiment Analyzer", layout="wide", page_icon="🤖")

st.title("🤖 News Mention, Summary & Sentiment Analyzer")
st.markdown("This tool scours the web for news about a specific person on a given day, then uses AI to summarize each article and analyze the sentiment of the mentions.")

col1, col2 = st.columns(2)
with col1:
    person_name = st.text_input("👤 **Person's Full Name**", placeholder="e.g., Taylor Swift")
    date_input = st.date_input("🗓️ **Date to Search**", datetime.now() - timedelta(days=1))
with col2:
    recipient_email = st.text_input("✉️ **Your Email Address (Optional)**", placeholder="Enter your email to receive the report")

if st.button("🚀 Generate Report", type="primary", use_container_width=True):
    if not person_name:
        st.warning("Please enter a person's name to start the analysis.")
        st.stop()

    from_date = date_input
    to_date = from_date + timedelta(days=1)
    
    with st.spinner(f"🔍 Searching NewsAPI for articles about '{person_name}'..."):
        newsapi_client = NewsApiClient(api_key=MY_API_KEY)
        # We only use NewsAPI now
        final_urls_list = sorted(list(set(fetch_from_newsapi(newsapi_client, person_name, from_date, to_date))))
    
    if not final_urls_list:
        st.error(f"No articles found for '{person_name}' on {from_date.strftime('%Y-%m-%d')}. Please try another name or date.")
        st.stop()

    st.success(f"Found {len(final_urls_list)} articles from NewsAPI. Now analyzing...")
    
    results = {}
    progress_bar = st.progress(0, text="Analyzing articles...")
    st.markdown("---")
    st.subheader("⚙️ Analysis Log")
    
    for i, url in enumerate(final_urls_list):
        title, mentions, article_text = process_article(url, person_name)
        
        if article_text:
            summary = get_summary_from_gpt(article_text)
            sentiment = get_sentiment_from_gpt(person_name, mentions) if mentions else "No mentions found."
            results[url] = {'title': title, 'summary': summary, 'mentions': mentions, 'sentiment': sentiment}
        
        progress_bar.progress((i + 1) / len(final_urls_list), text=f"Analyzing: {url[:80]}...")
    
    progress_bar.empty()
    st.success("✅ Analysis Complete!")
    if results:
        st.balloons()

    st.header("📊 Final Report", divider='rainbow')
    
    report_text_content = (f"News Report for {person_name} on {from_date.strftime('%A, %B %d, %Y')}\n" + "="*50 + "\n\n")

    if not results:
        st.warning("No articles could be successfully analyzed. They may have been empty, behind paywalls, or blocked access.")
    
    if results:
        report_text_content += "--- Analyzed Articles ---\n\n"
        for i, (url, data) in enumerate(results.items(), 1):
            with st.container(border=True):
                st.subheader(f"{i}. {data.get('title', 'Title Not Found')}", anchor=False)
                st.markdown(f"**Source:** [{url}]({url})")
                st.info(f"**AI Summary:** {data['summary']}")
                
                if "Positive" in data['sentiment']: st.success(f"**Sentiment:** {data['sentiment']}")
                elif "Negative" in data['sentiment']: st.error(f"**Sentiment:** {data['sentiment']}")
                else: st.warning(f"**Sentiment:** {data['sentiment']}")

                if data['mentions']:
                    with st.expander("Show mentions..."):
                        for sent in data['mentions']:
                            st.markdown(f'- "{sent}"')
            
            report_text_content += f"{i}. Title: {data.get('title', 'Title Not Found')}\n   URL: {url}\n\n   AI Summary: {data['summary']}\n\n   Sentiment Analysis: {data['sentiment']}\n"
            if data['mentions']:
                report_text_content += "   Mentions Found:\n"
                for sent in data['mentions']: report_text_content += f'   - "{sent}"\n'
            else:
                report_text_content += "   Mentions Found: None\n"
            report_text_content += "\n" + "="*50 + "\n\n"

    if recipient_email and results:
        with st.spinner("Preparing and sending email report..."):
            # The rest of the email code remains the same
            output_filename = f"Report-{person_name.replace(' ','_')}-{from_date.strftime('%Y-%m-%d')}.txt"
            with open(output_filename, "w", encoding='utf-8') as f:
                f.write(report_text_content)
            
            email_subject = f"News & Sentiment Report for {person_name} on {from_date.strftime('%Y-%m-%d')}"
            email_body = f"Hi,\n\nPlease find the attached news summary and sentiment report for {person_name} covering {from_date.strftime('%Y-%m-%d')}.\n\nBest wishes,\nYour Friendly News Bot"
            
            if send_email_with_attachment(email_subject, email_body, recipient_email, output_filename):
                st.success(f"✅ Report successfully sent to {recipient_email}!")
            else:
                st.error("Failed to send the email report.")
            
            if os.path.exists(output_filename):
                os.remove(output_filename)
