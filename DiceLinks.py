import requests
import logging
import pandas as pd
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime

DICE_URL = "https://www.dice.com/jobs?filters.postedDate=ONE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&countryCode=US&latitude=38.7945952&location=United+States&locationPrecision=Country&longitude=-106.5348379&q=Golang"
TELEGRAM_BOT_TOKEN = "8503178182:AAG2euQgRP2DkaDDPD_rrM9tLyZynshtHn8"
CHAT_ID = "-1003628736585"
EXCEL_FILE = 'dice_jobs_list.xlsx'

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

def end_msg_jobs_telegram(new_job_count):
    now = datetime.now().strftime("%B %d, %Y -- %I:%M %p")
    separator = "-" * 55
    payload = {
        "chat_id": CHAT_ID,
        "text": f"""
            ╔═════════════════════════════════════════════╗
            ║   DICE SCRAPER COMPLETED ✅                 ║
            ╠═════════════════════════════════════════════╣
            ║ ⏰ {now}                                    ║
            ║ 🆕 New Jobs: {str(new_job_count)}           ║
            ║ 📊 Status: SUCCESS                          ║
            ╚═════════════════════════════════════════════╝
                """,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(TELEGRAM_URL, json=payload)
        if response.status_code == 200:
            logging.info("Sent completion message to Telegram")
        else:
            logging.error(f"Failed to send completion message: {response.text}")
    except Exception as e:
        logging.error(f"Error sending completion message: {e}")


def send_jobs_to_telegram(df):
    for _, row in df.iterrows():
        message = (
            f"*{row['Title']}*\n"
            f"🏢 {row['Company'] or 'Unknown Company'}\n"
            f"📍 {row['Location'] or 'Location not listed'}\n"
            f"📝 Employment: {row['Employment_Type'] or 'N/A'}\n"
            f"💰 Salary: {row['Salary'] or 'N/A'}\n"
            f"🔗 [Apply here]({row['URL']})"
        )
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(TELEGRAM_URL, json=payload)
            if response.status_code == 200:
                logging.info(f"Sent job to Telegram: {row['Title']}")
            else:
                logging.error(f"Failed to send job: {response.text}")
            time.sleep(1)  # Avoid rate limits
        except Exception as e:
            logging.error(f"Error sending to Telegram: {e}")


def main():
    df_scraped = fetch_all_links(DICE_URL)

    if df_scraped.empty:
        print("No jobs found during scraping.")
        return
    df_new, df_existing = flt_exsis_links(df_scraped)

    if df_new.empty:
        print("\nℹ️  No new jobs found. All scraped jobs already exist in the database.")
        end_msg_jobs_telegram(0)
        return
    if save_to_excel(df_new, df_existing):
        print(f"💾 Successfully saved to {EXCEL_FILE}")
    print(len(df_new))
    send_jobs_to_telegram(df_new)
    end_msg_jobs_telegram(len(df_new))


if __name__ == "__main__":
    main()