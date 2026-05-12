# 🎲 Auto Dice Job Links

Automatically scrapes Golang contract job listings from [Dice.com](https://www.dice.com), scores them against your resume using ATS logic, sends matching jobs to Telegram, and emails recruiters — all on a schedule via GitHub Actions.

---

## 🚀 What It Does

- Scrapes Golang contract jobs from Dice.com every 27 minutes
- Filters out jobs already seen (deduplication via Excel)
- Fetches full job descriptions and extracts key details
- Calculates an **ATS match score** between your resume and each job
- Extracts recruiter email addresses from job pages
- **Sends emails** via Gmail API to recruiters for jobs with ATS score ≥ 45%
- Posts new job summaries to a **Telegram channel**
- Saves all results to `dice_jobs_list.xlsx` and commits it back to the repo

---

## 📁 Project Structure

```
├── DiceLinks.py              # Main scraper script
├── Dinesh_Go_Resume.docx     # Your resume (used for ATS scoring)
├── dice_jobs_list.xlsx       # Output: running log of all jobs found
├── requirements.txt          # Python dependencies
├── .github/
│   └── workflows/
│       └── dice_jobs.yml     # GitHub Actions workflow
├── .gitignore
└── README.md
```

> `credentials.json` and `token.json` are generated at runtime from GitHub Secrets and are never committed.

---

## ⚙️ Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/Auto_Job_Links.git
cd Auto_Job_Links
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|---|---|
| `GOOGLE_CREDENTIALS` | Contents of your `credentials.json` from Google Cloud Console |
| `GOOGLE_TOKEN` | Contents of your `token.json` (generated after first OAuth login) |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `CHAT_ID` | Your Telegram chat/channel ID |

### 4. Google Gmail API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Gmail API**
3. Create **OAuth 2.0 credentials** → Download as `credentials.json`
4. Run the script locally once to generate `token.json` via browser login
5. Copy the contents of both files into the GitHub Secrets above

---

## 🤖 GitHub Actions Workflow

The workflow runs automatically every 27 minutes and can also be triggered manually.

```
Schedule: */27 * * * *
Trigger:  workflow_dispatch (manual)
```

**Steps:**
1. Checkout repo
2. Set up Python 3.11
3. Install dependencies from `requirements.txt`
4. Write `credentials.json` and `token.json` from secrets
5. Run `DiceLinks.py`
6. Commit and push updated `dice_jobs_list.xlsx` to `main`

---

## 📊 Excel Output Columns

| Column | Description |
|---|---|
| Title | Job title |
| URL | Link to the job on Dice |
| Company | Hiring company |
| Location | Job location |
| Employment_Type | Contract / Third Party etc. |
| Salary | Listed salary if available |
| ATS_Score | Resume match score (%) |
| Badges | Job badges from listing |
| Email | Recruiter email extracted from page |
| Email_Sent | Y / N / N/A |
| Email_Not_Sent_Reason | Reason if email was not sent |

---

## 📬 Email Behavior

- Emails are only sent when ATS score is **≥ 45%** and a recruiter email is found
- Resume (`Dinesh_Go_Resume.docx`) is attached automatically
- Currently sends to test addresses — update `send_email_via_gmail()` in `DiceLinks.py` to use real recruiter emails when ready

---

## 🛠 Tech Stack

- **Python 3.11**
- `requests` + `beautifulsoup4` — scraping
- `pandas` + `openpyxl` — Excel management
- `scikit-learn` — TF-IDF ATS scoring
- `python-docx` — resume parsing
- `google-api-python-client` — Gmail sending
- **GitHub Actions** — automation & scheduling
- **Telegram Bot API** — job notifications

---

## ⚠️ Notes

- Dice.com may rate-limit or block repeated scraping. The script handles basic retries.
- The Gmail OAuth token expires periodically. If emails stop sending, re-generate `token.json` locally and update the secret.
- To stop tracking `dice_jobs_list.xlsx` in git, uncomment the relevant line in `.gitignore`.
