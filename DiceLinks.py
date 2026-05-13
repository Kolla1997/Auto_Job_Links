import requests
import logging
import pandas as pd
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime
import docx
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from zoneinfo import ZoneInfo 
import pytz
import base64

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
cst = pytz.timezone('America/Chicago')

# ─────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────
RESUME_PATH   = "Dinesh_Go_Resume.docx"
SENDER_NAME   = "Dinesh K"
SENDER_PHONE  = "(315) 232-1317"
SENDER_EMAIL  = "dineshkolla26@gmail.com"
SENDER_CITY   = "Chicago, IL"

# Gmail OAuth scopes
SCOPES        = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_FILE    = "token.json"          # saved after first login
CREDS_FILE    = "credentials.json"   # downloaded from Google Cloud Console

DICE_URL = "https://www.dice.com/jobs?filters.postedDate=ONE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&countryCode=US&latitude=38.7945952&location=United+States&locationPrecision=Country&longitude=-106.5348379&q=Golang"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
EXCEL_FILE = 'dice_jobs_list.xlsx'
resume_path = "Dinesh_Go_Resume.docx" 

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def process_job_links(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    jobs_data = []

    job_links = soup.find_all(
        "a",
        attrs={"data-testid": "job-search-job-detail-link"}
    )

    for job in job_links:
        title = job.get_text(strip=True)
        url = job.get("href")

        location_tag = job.find_next(
            "p", class_="text-sm font-normal text-zinc-600"
        )
        location = location_tag.get_text(strip=True) if location_tag else None

        employment_tag = job.find_next("p", id="employmentType-label")
        employment_type = (
            employment_tag.get_text(strip=True) if employment_tag else None
        )

        salary_tag = job.find_next("p", id="salary-label")
        salary = salary_tag.get_text(strip=True) if salary_tag else None

        company_tag = job.find_next(
            "p", class_="mb-0 line-clamp-2 text-sm sm:line-clamp-1"
        )
        company = company_tag.get_text(strip=True) if company_tag else None
        keywords = ["golang", "go developer", "go engineer", "go", "application support engineer", "backend"]

        if any(k in title.lower() for k in keywords):
            jobs_data.append({
                "Title": title,
                "URL": url,
                "Location": location,
                "Employment_Type": employment_type,
                "Salary": salary,
                "Company": company
            })

    return jobs_data

def fetch_all_links(dice_url):
    page_num = 0
    all_jobs = []

    while True:
        response = requests.get(dice_url, params={"page": page_num}, timeout=10)

        if response.status_code != 200:
            break

        page_jobs = process_job_links(response.text)

        if not page_jobs:
            break

        all_jobs.extend(page_jobs)
        page_num += 1

    return pd.DataFrame(all_jobs)

def load_existing_jobs():
    """Load existing jobs from Excel file"""
    if os.path.exists(EXCEL_FILE):
        try:
            df_existing = pd.read_excel(EXCEL_FILE, engine='openpyxl')
            logging.info(f"Loaded {len(df_existing)} existing jobs from {EXCEL_FILE}")
            return df_existing
        except Exception as e:
            logging.error(f"Error loading Excel file: {e}")
            return pd.DataFrame()
    else:
        logging.info("No existing Excel file found. Will create new one.")
        return pd.DataFrame()

def save_to_excel(df_new, df_existing):
    """Save or append jobs to Excel file"""
    try:
        if df_existing.empty:
            df_new.to_excel(EXCEL_FILE, index=False, engine='openpyxl')
            logging.info(f"Created new Excel file: {EXCEL_FILE}")
        else:
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            # Remove duplicates based on URL
            df_combined = df_combined.drop_duplicates(subset=['URL'], keep='first')
            df_combined.to_excel(EXCEL_FILE, index=False, engine='openpyxl')
            logging.info(f"Updated Excel file with {len(df_new)} new jobs")
        return True
    except Exception as e:
        logging.error(f"Error saving to Excel: {e}")
        return False

def flt_exsis_links(df_scraped):
    """Filter out existing jobs and return only new ones"""
    df_existing = load_existing_jobs()

    if df_existing.empty:
        logging.info("No existing data. All scraped jobs are new.")
        return df_scraped, df_existing
    existing_urls = set(df_existing['URL'].tolist())
    df_new = df_scraped[~df_scraped['URL'].isin(existing_urls)]

    logging.info(f"Found {len(df_new)} new jobs out of {len(df_scraped)} scraped jobs")
    return df_new, df_existing

def send_telegram_message(message, max_retries=3):
    """Send message to Telegram with retry logic for rate limiting"""
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(TELEGRAM_URL, json=payload, timeout=10)
            
            if response.status_code == 200:
                return True
            elif response.status_code == 429:
                # Rate limit hit - extract retry_after time
                try:
                    error_data = response.json()
                    retry_after = error_data.get('parameters', {}).get('retry_after', 30)
                except:
                    retry_after = 30
                
                logging.warning(f"Rate limit hit. Waiting {retry_after} seconds...")
                time.sleep(retry_after + 1)  # Add 1 second buffer
                continue
            else:
                logging.error(f"Failed to send message: {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Error sending to Telegram (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
    
    return False

def end_msg_jobs_telegram(new_job_count):
    now = datetime.now(cst).strftime("%B %d, %Y -- %I:%M %p CST")
    if new_job_count >0:
        message = f"""
                ╔═════════════════════════════════════════════╗
                ║   DICE SCRAPER COMPLETED ✅                 ║
                ╠═════════════════════════════════════════════╣
                ║ ⏰ {now}                                    ║
                ║ 🆕 New Jobs: {str(new_job_count)}           ║
                ║ 📊 Status: SUCCESS                          ║
                ╚═════════════════════════════════════════════╝
        """
    else:
        message = f"""
                ╔═════════════════════════════════════════════╗
                ║   DICE SCRAPER COMPLETED ✅                ║
                ╠═════════════════════════════════════════════╣
                ║ ⏰ {now}                                   ║
                ║ 🆕 No new jobs found.                      ║
                ╚═════════════════════════════════════════════╝
        """
    
    if send_telegram_message(message):
        logging.info("Sent completion message to Telegram")
    else:
        logging.error("Failed to send completion message after retries")


def send_jobs_to_telegram(df):
    for idx, row in df.iterrows():
        sent_status = row['Email_Sent']
        status_icon = "✅" if sent_status == "Y" else "❌" if sent_status == "N" else "⏳"
        message = (
            f"<b>{row['Title']}</b>\n"
            f"🏢 {row['Company'] or 'Unknown Company'}\n"
            f"📍 {row['Location'] or 'Location not listed'}\n"
            f"📝 Employment: {row['Employment_Type'] or 'N/A'}\n"
            f"💰 Salary: {row['Salary'] or 'N/A'}\n"
            f"📊 ATS Score: {row['ATS_Score'] or 'N/A'}\n"
            f"🏷️ Badges: {row['Badges'] or 'N/A'}\n"
            f"📧 Email: {row['Email'] or 'N/A'}\n"
            f"{status_icon} Email Sent: {row['Email_Sent'] or 'N/A'}\n"
            f"⚠️ Remarks: {row['Email_Not_Sent_Reason'] or 'N/A'}\n"
            f'🔗 <a href="{row["URL"]}">Apply Now</a>'
        )
        
        if send_telegram_message(message):
            logging.info(f"Sent job {idx + 1}/{len(df)} to Telegram: {row['Title']}")
        else:
            logging.error(f"Failed to send job: {row['Title']}")
        
        # Wait between messages to respect rate limits
        time.sleep(1)

def process_dice_description(html_text):
    soup = BeautifulSoup(html_text, "html.parser")

    job_data = {
        "Title": None,
        "Company": None,
        "Location": None,
        "Experience": None,
        "Duration": None,
        "Employment_Type": None,
        "Badges": [],
        "Sections": {},
        "Full_Text": None
    }

    # 1. Header Extraction (Same as before)
    header_card = soup.find("div", {"data-testid": "job-detail-header-card"})
    if header_card:
        title_tag = header_card.find("h1")
        if title_tag: job_data["Title"] = title_tag.get_text(strip=True)
        
        company_tag = header_card.find("a", href=re.compile("company-profile"))
        if company_tag: job_data["Company"] = company_tag.get_text(strip=True)
            
        badge_container = header_card.find("div", class_=re.compile("items-start|badge"))
        if badge_container:
            badges = badge_container.find_all("div", class_=re.compile("SeuiInfoBadge|badge"))
            job_data["Badges"] = " | ".join([b.get_text(strip=True) for b in badges])

    # 2. Container Target
    container = soup.find("div", class_=re.compile("jobDescription|description"))
    if not container:
        container = soup.find("body") or soup

    # 3. Process Metadata (Enhanced for Duration)
    for p in container.find_all(["p", "div", "li"]):
        full_line = p.get_text(" ", strip=True)
        if not full_line: continue

        # Lowercase version for easier searching
        lower_line = full_line.lower()

        # Check for keywords anywhere in the line, not just the 'strong' tag
        if "position:" in lower_line or "job title:" in lower_line:
            if not job_data["Title"]:
                job_data["Title"] = re.sub(r"(job title|position):\s*", "", full_line, flags=re.I).strip()
        
        if "location:" in lower_line:
            # If duration is in the same line, split them or extract specifically
            job_data["Location"] = re.search(r"Location:\s*(.*?)(?=Duration:|$)", full_line, re.I).group(1).strip()
        
        if "duration:" in lower_line:
            # This regex captures everything after 'Duration:' until the end of the line
            match = re.search(r"Duration:\s*(.*)", full_line, re.I)
            if match:
                job_data["Duration"] = match.group(1).strip()

        if "experience:" in lower_line:
            job_data["Experience"] = re.sub(r"experience:\s*", "", full_line, flags=re.I).strip()

        if "employment type:" in lower_line:
            job_data["Employment_Type"] = re.sub(r"employment type:\s*", "", full_line, flags=re.I).strip()

    # 4. Extract Sections (Bullet points)
    # We look for the bold headers that usually precede lists
    for strong in container.find_all("strong"):
        section_title = strong.get_text(strip=True)
        # Skip standard metadata labels
        if section_title.lower().rstrip(':') in ['position', 'location', 'duration', 'experience', 'main skills']:
            continue
            
        ul = strong.find_next("ul")
        if ul:
            items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
            if items:
                job_data["Sections"][section_title] = items

    job_data["Full_Text"] = container.get_text(" ", strip=True)
    return job_data

def fetch_job_details(job_url):
    response = requests.get(job_url, timeout=10)
    if response.status_code == 200:
        return process_dice_description(response.text)
    return None

def read_word_resume(file_path):
    """Safely extracts and cleans text from a .docx file."""
    try:
        doc = docx.Document(file_path)
        # Filter out empty lines to keep the 'signal' high
        text = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return " ".join(text)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return None

def extract_jd_keywords(jd_dict):
    """
    Specifically extracts high-value keywords from the JD dictionary.
    Focuses on 'Must have' and 'Nice to have' to mimic real ATS logic.
    """
    keywords = []
    
    # 1. Grab hardcoded skill lists if they exist
    sections = jd_dict.get('Sections', {})
    must_have = sections.get('Must have skills:', [])
    nice_have = sections.get('Nice to have skills:', [])
    
    keywords.extend(must_have)
    keywords.extend(nice_have)
    
    # 2. Grab the title
    if jd_dict.get('Title'):
        keywords.append(jd_dict['Title'])
        
    # 3. If keywords are still empty, fallback to the full text
    if not keywords:
        return jd_dict.get('Full_Text', "")
        
    return " ".join(keywords)

def calculate_ats_score(resume_text, jd_keywords):
    """
    Combines Keyword Presence (Boolean) with Contextual Similarity (TF-IDF).
    This creates a much more realistic 'Simplify-style' score.
    """
    # Clean and lowercase everything
    res_clean = re.sub(r'[^\w\s]', ' ', resume_text).lower()
    jd_clean = re.sub(r'[^\w\s]', ' ', jd_keywords).lower()
    
    # --- 1. KEYWORD MATCHING (Smarter than pure math) ---
    jd_words = set(jd_clean.split())
    res_words = set(res_clean.split())
    
    found_keywords = jd_words.intersection(res_words)
    keyword_score = (len(found_keywords) / len(jd_words)) if jd_words else 0
    
    # --- 2. CONTEXTUAL MATCHING (TF-IDF) ---
    vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
    try:
        tfidf = vectorizer.fit_transform([res_clean, jd_clean])
        context_score = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
    except:
        context_score = 0

    # Weighted Average: 70% Keyword Presence, 30% Context/Frequency
    final_score = (keyword_score * 0.7) + (context_score * 0.3)
    return round(final_score * 100, 2)


def ATS_cal(resume_content,JD_data):
    if not resume_content:
        print("Could not process the resume. Please check the file path.")
    jd_keywords = extract_jd_keywords(JD_data)
    match_score = calculate_ats_score(resume_content, jd_keywords)
    return f"{match_score}%"


def extract_email_from_page(url: str) -> str:
    """
    Fetches the raw HTML of a job page and extracts any email addresses.
    Returns a comma-separated string of unique emails, or 'N/D' if none found.
    """
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    EMAIL_REGEX = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    
    # Domains/patterns that are almost always false positives
    EXCLUDED_PATTERNS = {
        "sentry", "example", "domain", "email", "user", "test",
        "noreply", "no-reply", "placeholder"
    }
    EXCLUDED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "woff", "woff2", "css", "js"}

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        raw_html = response.text

        raw_emails = re.findall(EMAIL_REGEX, raw_html)

        filtered = set()
        for email in raw_emails:
            ext = email.split(".")[-1].lower()
            lower = email.lower()
            if ext in EXCLUDED_EXTENSIONS:
                continue
            if any(pat in lower for pat in EXCLUDED_PATTERNS):
                continue
            filtered.add(email)

        return ", ".join(sorted(filtered)) if filtered else "N/A"

    except Exception as e:
        print(f"⚠️  Email extraction failed for {url}: {e}")
        return "N/A"
    
# ─────────────────────────────────────────────────────────────────
# GMAIL AUTH
# ─────────────────────────────────────────────────────────────────
def get_gmail_service():
    """
    Authenticates via OAuth2 and returns an authenticated Gmail service.
    On first run it opens a browser window for you to approve access.
    After that, the token is cached in token.json.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# ─────────────────────────────────────────────────────────────────
# EMAIL BUILDER — template with dynamic Job Title
# ─────────────────────────────────────────────────────────────────
def build_email_body(job_title: str) -> str:
    """
    Returns the email body with the fetched job title inserted dynamically.
    Falls back to 'Software Developer' if no title is available.
    """
    title = job_title.strip() if job_title else "Golang Developer"

    body = f"""
        <html>
          <body style="font-family: Verdana, sans-serif; font-size: 12px; color: #333333;">
            <p>Hi, Greetings of the day.<br>
            I hope you are doing well.</p>
            <p>I came across the <strong>{title}</strong> position you posted on Dice, and I wanted to let you know that I'm interested. I have 7 years of professional experience in software development, specializing in Golang-based backend systems, microservices architecture, and distributed cloud-native applications.</p>
            <p>In my recent roles at Midwest Good Inc. and Optum, I've designed and deployed scalable Golang services on AWS, integrated LangChain/OpenAI APIs for predictive automation, and implemented CI/CD pipelines using GitHub Actions and Jenkins.</p>
            <p>I've attached my resume for your review and would appreciate the opportunity to discuss how my experience aligns with your current opening.</p>
            <p>--<br>
            Best Regards,<br>
            <strong>{SENDER_NAME}</strong><br>
            {SENDER_PHONE}<br>
            {SENDER_EMAIL}<br>
            {SENDER_CITY}</p>
          </body>
        </html>
        """
    return body

# ─────────────────────────────────────────────────────────────────
# SEND EMAIL VIA GMAIL API
# ─────────────────────────────────────────────────────────────────
def send_email_via_gmail(service, to_email: str, job_title: str, resume_path: str) -> bool:
    """
    Composes and sends an email with the resume attached using Gmail API.
    Returns True on success, False on failure.
    """
    try:
        title   = job_title.strip() if job_title else "Golang Developer"
        subject = f"Interested in {title} Position"
        body    = build_email_body(title)

        # Build MIME message
        msg = MIMEMultipart()
        msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg["To"]      = to_email
        msg["Cc"]      = 'charan@symploreus.com'
        # msg["To"]      = "dkolla1997@gmail.com"
        msg["Bcc"]      = "kolladinesh26@gmail.com"
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        # Attach resume if file exists
        if resume_path and os.path.exists(resume_path):
            with open(resume_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(resume_path)
                part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(part)
            print(f"   📎 Resume attached: {filename}")
        else:
            print(f"   ⚠️  Resume not found at '{resume_path}' — sending without attachment.")

        # Encode and send
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"   ✅ Email sent to: {to_email} | Subject: {subject}")
        return True

    except Exception as e:
        print(f"   ❌ Failed to send email to {to_email}: {e}")
        return False

def main():
    resume_content = read_word_resume(resume_path)
    
    # Authenticate Gmail once — reused for all emails in this run
    print("🔐 Authenticating Gmail...")
    gmail_service = get_gmail_service()
    print("✅ Gmail authenticated.\n")

    df_scraped = fetch_all_links(DICE_URL)
    df_scraped = df_scraped.drop_duplicates(subset=['URL'], keep='first')

    if df_scraped.empty:
        print("No jobs found during scraping.")
        end_msg_jobs_telegram(0)
        return
    df_new_raw, df_existing = flt_exsis_links(df_scraped)
    df_new = df_new_raw.copy()
    df_new['Job_JD'] = None
    df_new['ATS_Score'] = None
    df_new['Badges'] = None
    df_new['Email']     = None
    df_new["Email_Sent"]   = None
    df_new["Email_Not_Sent_Reason"] = None

    if df_new.empty:
        print("No jobs found during scraping.")
        end_msg_jobs_telegram(0)
        return
    for index, row in df_new.iterrows():
        JD_data = fetch_job_details(row['URL'])
        score = ATS_cal(resume_content,JD_data)
        df_new.at[index, 'ATS_Score'] = str(score)
        email = extract_email_from_page(row['URL'])
        df_new.at[index, 'Email'] = email

        if JD_data:
            job_title = JD_data.get("Title", "")
            score = ATS_cal(resume_content, JD_data)
            df_new.at[index, 'ATS_Score'] = f"{score}%"
            df_new.at[index, 'Company']   = JD_data.get('Company', "")
            df_new.at[index, 'Badges']    = JD_data.get('Badges', "")
            df_new.at[index, 'Title']     = JD_data.get('Title', "")
            df_new.at[index, 'Job_JD']    = str(JD_data.get('Full_Text', ""))
        
        # ── 3. Send email if address was found ──────────────────
        score_value = float(str(score).replace('%', ''))
        if score and score_value >= 45:  # Only attempt to send if ATS score is 45% or higher
            if email and email != "N/A":
                # Handle multiple comma-separated emails on one listing
                for single_email in [e.strip() for e in email.split(",")]:
                    sent = send_email_via_gmail(
                        service     = gmail_service,
                        to_email    = single_email,
                        job_title   = job_title,
                        resume_path = RESUME_PATH,
                    )
                    df_new.at[index, "Email_Sent"] = "Y" if sent else "N"
                    if not sent:
                        df_new.at[index, "Email_Not_Sent_Reason"] = "Gmail API error"
                    else:
                        df_new.at[index, "Email_Not_Sent_Reason"] = "Sent successfully"
            else:
                df_new.at[index, "Email_Sent"] = "N/A"
                df_new.at[index, "Email_Not_Sent_Reason"] = "No email"
                print("   ⏭️  No email found — skipping send.")
        else:
            df_new.at[index, "Email_Sent"] = "N/A"
            df_new.at[index, "Email_Not_Sent_Reason"] = "Less ATS score"

    if save_to_excel(df_new, df_existing):
        print(f"💾 Successfully saved to {EXCEL_FILE}")
    print(f"📤 Sending {len(df_new)} new jobs to Telegram...")
    send_jobs_to_telegram(df_new)
    time.sleep(2)
    end_msg_jobs_telegram(len(df_new))

if __name__ == "__main__":
    main()
