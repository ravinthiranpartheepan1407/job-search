import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import time
import json
from urllib.parse import quote_plus, urljoin, urlparse
import re
from difflib import SequenceMatcher

# Page configuration
st.set_page_config(
    page_title="Deep IT Service Desk Job Scraper",
    page_icon="💼",
    layout="wide"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 36px;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 20px;
    }
    .live-indicator {
        display: inline-block;
        width: 10px;
        height: 10px;
        background-color: #00ff00;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'all_jobs' not in st.session_state:
    st.session_state.all_jobs = []
if 'last_update' not in st.session_state:
    st.session_state.last_update = None
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False
if 'removed_duplicates' not in st.session_state:
    st.session_state.removed_duplicates = 0

# Comprehensive job search keywords
JOB_KEYWORDS = [
    "IT Service Desk",
    "Help Desk",
    "Technical Support",
    "IT Support",
    "Service Desk Analyst",
    "Desktop Support",
    "IT Helpdesk",
    "Technical Support Engineer",
    "IT Support Engineer",
    "Service Desk Engineer",
    "L1 Support",
    "L2 Support",
    "IT Operations",
    "System Administrator"
]


def normalize_text(text):
    """Normalize text for comparison"""
    if not text:
        return ""
    # Convert to lowercase, remove extra spaces, special chars
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def similarity_ratio(str1, str2):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, normalize_text(str1), normalize_text(str2)).ratio()


def is_duplicate(job1, job2, threshold=0.85):
    """
    Check if two jobs are duplicates based on multiple criteria
    Returns True if jobs are considered duplicates
    """
    # Exact match on title + company
    if (normalize_text(job1['title']) == normalize_text(job2['title']) and
            normalize_text(job1['company']) == normalize_text(job2['company'])):
        return True

    # High similarity on title + same company
    title_similarity = similarity_ratio(job1['title'], job2['title'])
    company_similarity = similarity_ratio(job1['company'], job2['company'])

    if title_similarity >= threshold and company_similarity >= 0.9:
        return True

    # Same URL (if available and not generic)
    if (job1.get('url') and job2.get('url') and
            job1['url'] == job2['url'] and
            'search' not in job1['url'].lower()):
        return True

    return False


def remove_duplicates(jobs_list, similarity_threshold=0.85):
    """
    Remove duplicate jobs from a list
    Returns: (unique_jobs, num_duplicates_removed)
    """
    if not jobs_list:
        return [], 0

    unique_jobs = []
    duplicates_removed = 0

    for job in jobs_list:
        is_dup = False
        for unique_job in unique_jobs:
            if is_duplicate(job, unique_job, similarity_threshold):
                is_dup = True
                duplicates_removed += 1
                break

        if not is_dup:
            unique_jobs.append(job)

    return unique_jobs, duplicates_removed


def get_headers():
    """Return rotating headers for requests"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    return {
        'User-Agent': user_agents[int(time.time()) % len(user_agents)],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
    }


def deep_scrape_naukri(location="India", work_mode="remote,hybrid"):
    """Deep scrape Naukri.com with pagination"""
    jobs = []
    keywords_list = ["it-service-desk-jobs"]

    try:
        for keyword in keywords_list:
            # Multiple pages
            for page in range(1, 4):  # First 3 pages
                try:
                    clean_keyword = keyword.replace(" ", "-")
                    url = f"https://www.naukri.com/{clean_keyword}-jobs-in-{location}-{page}"

                    response = requests.get(url, headers=get_headers(), timeout=20)

                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')

                        # Try multiple selectors
                        job_articles = soup.find_all('article', class_='jobTuple') or \
                                       soup.find_all('div', class_='jobTuple') or \
                                       soup.find_all('div', {'data-job-id': True})

                        for job in job_articles:
                            try:
                                # Title
                                title_elem = job.find('a', class_='title') or job.find('div', class_='title')
                                if not title_elem:
                                    continue

                                title = title_elem.text.strip()
                                job_url = title_elem.get('href', '') if title_elem.name == 'a' else ''

                                # Company
                                company_elem = job.find('a', class_='subTitle') or job.find('div', class_='companyInfo')
                                company = company_elem.text.strip() if company_elem else 'N/A'

                                # Location
                                location_elem = job.find('li', class_='location') or job.find('span', class_='location')
                                loc = location_elem.text.strip() if location_elem else location

                                # Experience
                                exp_elem = job.find('li', class_='experience') or job.find('span', class_='experience')
                                exp = exp_elem.text.strip() if exp_elem else 'Not specified'

                                # Salary
                                sal_elem = job.find('li', class_='salary') or job.find('span', class_='salary')
                                salary = sal_elem.text.strip() if sal_elem else 'Not disclosed'

                                # Posted date
                                date_elem = job.find('span', class_='jobTupleFooter')
                                posted = date_elem.text.strip() if date_elem else datetime.now().strftime('%Y-%m-%d')

                                jobs.append({
                                    'title': title,
                                    'company': company,
                                    'location': loc,
                                    'work_mode': 'Remote/Hybrid',
                                    'experience': exp,
                                    'salary': salary,
                                    'source': 'Naukri.com',
                                    'url': f"https://www.naukri.com{job_url}" if job_url.startswith('/') else job_url,
                                    'date_posted': posted,
                                    'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })
                            except Exception as e:
                                continue

                    time.sleep(2)  # Respectful delay
                except Exception as e:
                    continue

    except Exception as e:
        st.warning(f"Naukri.com: {str(e)}")

    return jobs


def deep_scrape_linkedin(location="India"):
    """Deep scrape LinkedIn with multiple searches"""
    jobs = []
    keywords_list = ["IT service desk", "help desk",
                     "service desk analyst", "desktop support", "L1 support"]

    try:
        for keyword in keywords_list:
            # Remote and Hybrid
            for work_type in ["2", "3"]:  # 2=Remote, 3=Hybrid
                try:
                    # Multiple pages
                    for start in [0, 25, 50]:  # Pagination
                        url = f"https://www.linkedin.com/jobs/search?keywords={quote_plus(keyword)}&location={location}&f_WT={work_type}&start={start}"

                        response = requests.get(url, headers=get_headers(), timeout=20)

                        if response.status_code == 200:
                            soup = BeautifulSoup(response.content, 'html.parser')

                            # Multiple selectors
                            job_cards = soup.find_all('div', class_='base-card') or \
                                        soup.find_all('div', class_='job-search-card') or \
                                        soup.find_all('li', class_='jobs-search-results__list-item')

                            for card in job_cards:
                                try:
                                    # Title
                                    title_elem = card.find('h3', class_='base-search-card__title') or \
                                                 card.find('a', class_='base-card__full-link') or \
                                                 card.find('h3')

                                    if not title_elem:
                                        continue

                                    title = title_elem.text.strip()

                                    # Company
                                    company_elem = card.find('h4', class_='base-search-card__subtitle') or \
                                                   card.find('a', class_='hidden-nested-link') or \
                                                   card.find('h4')
                                    company = company_elem.text.strip() if company_elem else 'N/A'

                                    # Location
                                    location_elem = card.find('span', class_='job-search-card__location') or \
                                                    card.find('span', class_='job-card-container__metadata-item')
                                    loc = location_elem.text.strip() if location_elem else location

                                    # URL
                                    link_elem = card.find('a', class_='base-card__full-link')
                                    job_url = link_elem.get('href', '') if link_elem else url

                                    # Posted time
                                    time_elem = card.find('time')
                                    posted = time_elem.get('datetime', datetime.now().strftime(
                                        '%Y-%m-%d')) if time_elem else datetime.now().strftime('%Y-%m-%d')

                                    jobs.append({
                                        'title': title,
                                        'company': company,
                                        'location': loc,
                                        'work_mode': 'Remote' if work_type == '2' else 'Hybrid',
                                        'experience': 'See posting',
                                        'salary': 'Not disclosed',
                                        'source': 'LinkedIn',
                                        'url': job_url,
                                        'date_posted': posted,
                                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    })
                                except Exception as e:
                                    continue

                        time.sleep(2)
                except Exception as e:
                    continue

    except Exception as e:
        st.warning(f"LinkedIn: {str(e)}")

    return jobs


def deep_scrape_indeed(location="India"):
    """Deep scrape Indeed India"""
    jobs = []
    keywords_list = ["it+service+desk"]

    try:
        for keyword in keywords_list:
            # Multiple pages and work modes
            for start in [0, 10, 20, 30]:  # 4 pages
                for remote_filter in ["remotejob", "hybrid"]:
                    try:
                        url = f"https://in.indeed.com/jobs?q={quote_plus(keyword)}&l={location}&{remote_filter}=1&start={start}"

                        response = requests.get(url, headers=get_headers(), timeout=20)

                        if response.status_code == 200:
                            soup = BeautifulSoup(response.content, 'html.parser')

                            # Multiple selectors
                            job_cards = soup.find_all('div', class_='job_seen_beacon') or \
                                        soup.find_all('td', class_='resultContent') or \
                                        soup.find_all('a', class_='jcs-JobTitle')

                            for card in job_cards:
                                try:
                                    # Title
                                    title_elem = card.find('h2', class_='jobTitle') or \
                                                 card.find('a', class_='jcs-JobTitle') or \
                                                 card.find('span', title=True)

                                    if not title_elem:
                                        continue

                                    title = title_elem.text.strip()

                                    # Company
                                    company_elem = card.find('span', {'data-testid': 'company-name'}) or \
                                                   card.find('span', class_='companyName')
                                    company = company_elem.text.strip() if company_elem else 'N/A'

                                    # Location
                                    location_elem = card.find('div', {'data-testid': 'text-location'}) or \
                                                    card.find('div', class_='companyLocation')
                                    loc = location_elem.text.strip() if location_elem else location

                                    # Salary
                                    salary_elem = card.find('div', class_='salary-snippet')
                                    salary = salary_elem.text.strip() if salary_elem else 'Not disclosed'

                                    # URL
                                    link_elem = card.find('a', class_='jcs-JobTitle')
                                    job_url = f"https://in.indeed.com{link_elem['href']}" if link_elem and link_elem.get(
                                        'href') else url

                                    # Posted
                                    date_elem = card.find('span', class_='date')
                                    posted = date_elem.text.strip() if date_elem else datetime.now().strftime(
                                        '%Y-%m-%d')

                                    jobs.append({
                                        'title': title,
                                        'company': company,
                                        'location': loc,
                                        'work_mode': 'Remote' if remote_filter == 'remotejob' else 'Hybrid',
                                        'experience': 'See posting',
                                        'salary': salary,
                                        'source': 'Indeed India',
                                        'url': job_url,
                                        'date_posted': posted,
                                        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    })
                                except Exception as e:
                                    continue

                        time.sleep(2)
                    except Exception as e:
                        continue

    except Exception as e:
        st.warning(f"Indeed India: {str(e)}")

    return jobs


def deep_scrape_google_jobs(location="India"):
    """Deep scrape Google Jobs"""
    jobs = []
    keywords_list = ["IT service desk", "help desk", "technical support", "IT support engineer",
                     "service desk analyst", "desktop support engineer"]

    try:
        for keyword in keywords_list:
            for work_mode in ["remote", "hybrid"]:
                try:
                    query = f"{keyword} {work_mode} {location}"
                    url = f"https://www.google.com/search?q={quote_plus(query)}&ibp=htl;jobs&htidocid="

                    response = requests.get(url, headers=get_headers(), timeout=20)

                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')

                        # Google Jobs specific selectors
                        job_cards = soup.find_all('div', class_='PwjeAc') or \
                                    soup.find_all('li', class_='iFjolb') or \
                                    soup.find_all('div', {'data-ved': True})

                        for card in job_cards[:10]:  # Limit per search
                            try:
                                # Extract job data from Google's structure
                                title_elem = card.find('div', class_='BjJfJf')
                                if not title_elem:
                                    continue

                                title = title_elem.text.strip()

                                # Company
                                company_elem = card.find('div', class_='vNEEBe')
                                company = company_elem.text.strip() if company_elem else 'N/A'

                                # Location
                                location_elem = card.find('div', class_='Qk80Jf')
                                loc = location_elem.text.strip() if location_elem else location

                                jobs.append({
                                    'title': title,
                                    'company': company,
                                    'location': loc,
                                    'work_mode': work_mode.capitalize(),
                                    'experience': 'See posting',
                                    'salary': 'Not disclosed',
                                    'source': 'Google Jobs',
                                    'url': url,
                                    'date_posted': datetime.now().strftime('%Y-%m-%d'),
                                    'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })
                            except Exception as e:
                                continue

                    time.sleep(2)
                except Exception as e:
                    continue

    except Exception as e:
        st.warning(f"Google Jobs: {str(e)}")

    return jobs


def deep_scrape_foundit(location="India"):
    """Deep scrape Foundit (Monster India)"""
    jobs = []
    keywords_list = ["IT service desk", "help desk", "technical support", "IT support"]

    try:
        for keyword in keywords_list:
            try:
                clean_keyword = quote_plus(keyword)
                url = f"https://www.foundit.in/srp/results?query={clean_keyword}&locations={location}"

                response = requests.get(url, headers=get_headers(), timeout=20)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')

                    job_cards = soup.find_all('div', class_='jobTuple') or \
                                soup.find_all('article', class_='cardWrap')

                    for card in job_cards:
                        try:
                            title_elem = card.find('a', {'data-test-id': 'job-title'}) or card.find('h3')
                            if not title_elem:
                                continue

                            title = title_elem.text.strip()

                            company_elem = card.find('a', {'data-test-id': 'company-name'}) or card.find('p',
                                                                                                         class_='company')
                            company = company_elem.text.strip() if company_elem else 'N/A'

                            location_elem = card.find('span', class_='location')
                            loc = location_elem.text.strip() if location_elem else location

                            exp_elem = card.find('span', class_='experience')
                            exp = exp_elem.text.strip() if exp_elem else 'Not specified'

                            salary_elem = card.find('span', class_='salary')
                            salary = salary_elem.text.strip() if salary_elem else 'Not disclosed'

                            job_url = title_elem.get('href', url) if title_elem.name == 'a' else url

                            jobs.append({
                                'title': title,
                                'company': company,
                                'location': loc,
                                'work_mode': 'Remote/Hybrid',
                                'experience': exp,
                                'salary': salary,
                                'source': 'Foundit',
                                'url': job_url,
                                'date_posted': datetime.now().strftime('%Y-%m-%d'),
                                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                        except Exception as e:
                            continue

                time.sleep(2)
            except Exception as e:
                continue

    except Exception as e:
        st.warning(f"Foundit: {str(e)}")

    return jobs


def deep_scrape_instahyre():
    """Deep scrape Instahyre"""
    jobs = []

    try:
        keywords_list = ["IT service desk", "help desk", "technical support"]

        for keyword in keywords_list:
            url = f"https://www.instahyre.com/search-jobs/?q={quote_plus(keyword)}&remote=true"

            response = requests.get(url, headers=get_headers(), timeout=20)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')

                job_cards = soup.find_all('div', class_='job-card-component')

                for card in job_cards:
                    try:
                        title_elem = card.find('p', class_='job-title')
                        if not title_elem:
                            continue

                        title = title_elem.text.strip()

                        company_elem = card.find('p', class_='company-name')
                        company = company_elem.text.strip() if company_elem else 'N/A'

                        location_elem = card.find('span', class_='job-location')
                        loc = location_elem.text.strip() if location_elem else 'Remote - India'

                        exp_elem = card.find('span', class_='experience')
                        exp = exp_elem.text.strip() if exp_elem else 'Not specified'

                        salary_elem = card.find('span', class_='salary')
                        salary = salary_elem.text.strip() if salary_elem else 'Not disclosed'

                        jobs.append({
                            'title': title,
                            'company': company,
                            'location': loc,
                            'work_mode': 'Remote',
                            'experience': exp,
                            'salary': salary,
                            'source': 'Instahyre',
                            'url': url,
                            'date_posted': datetime.now().strftime('%Y-%m-%d'),
                            'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                    except Exception as e:
                        continue

            time.sleep(2)

    except Exception as e:
        st.warning(f"Instahyre: {str(e)}")

    return jobs


def scrape_all_sources(location="India", work_modes=["remote"], dedup_threshold=0.85):
    """Deep scrape all job sources with automatic deduplication"""
    all_jobs = []

    sources = [
        ("LinkedIn (Deep)", lambda: deep_scrape_linkedin(location)),
        ("Naukri.com (Deep)", lambda: deep_scrape_naukri(location, ",".join(work_modes))),
        # ("Indeed India (Deep)", lambda: deep_scrape_indeed(location)),
        ("Google Jobs (Deep)", lambda: deep_scrape_google_jobs(location)),
        # ("Foundit (Deep)", lambda: deep_scrape_foundit(location)),
        # ("Instahyre (Deep)", deep_scrape_instahyre),
    ]

    progress_bar = st.progress(0)
    status_text = st.empty()
    result_container = st.container()

    for idx, (name, scraper) in enumerate(sources):
        status_text.text(f"🔍 Deep scraping {name}... This may take a while.")

        with result_container:
            start_time = time.time()
            try:
                jobs = scraper()
                elapsed = time.time() - start_time

                if len(jobs) > 0:
                    # Remove duplicates within this source
                    unique_jobs, source_dups = remove_duplicates(jobs, dedup_threshold)

                    st.success(
                        f"✅ {name}: Found **{len(jobs)}** jobs, **{len(unique_jobs)}** unique (removed {source_dups} duplicates) in {elapsed:.1f}s")
                    all_jobs.extend(unique_jobs)
                else:
                    st.info(f"ℹ️ {name}: No jobs found")
            except Exception as e:
                st.error(f"❌ {name}: {str(e)}")

        progress_bar.progress((idx + 1) / len(sources))

    status_text.empty()
    progress_bar.empty()

    # Final deduplication across all sources
    if all_jobs:
        final_jobs, cross_source_dups = remove_duplicates(all_jobs, dedup_threshold)
        if cross_source_dups > 0:
            st.info(f"🔄 Removed **{cross_source_dups}** additional cross-source duplicates")
        return final_jobs, cross_source_dups

    return all_jobs, 0


# Main App UI
st.markdown('<div class="main-header">💼 Suba Job Search</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")

    st.subheader("🌍 Location")
    location_option = st.selectbox(
        "Select Location",
        ["India", "Bangalore", "Mumbai", "Delhi NCR", "Hyderabad",
         "Chennai", "Pune", "Kolkata", "Ahmedabad"],
        index=0
    )

    if location_option == "Custom":
        custom_location = st.text_input("Enter Location", "India")
        selected_location = custom_location
    else:
        selected_location = location_option

    st.markdown("---")

    st.subheader("💼 Work Mode")
    work_modes = st.multiselect(
        "Select Work Modes",
        ["Remote", "Hybrid", "On-site"],
        default=["Remote"]
    )

    st.markdown("---")

    st.subheader("🔧 Deduplication")
    dedup_threshold = st.slider(
        "Similarity Threshold",
        min_value=0.7,
        max_value=1.0,
        value=0.85,
        step=0.05,
        help="Higher = stricter matching (0.85 recommended)"
    )

    st.caption(f"Jobs with {int(dedup_threshold * 100)}%+ duplicates")

    st.markdown("---")

    st.subheader("🔄 Auto-Refresh")
    auto_refresh = st.checkbox("Enable Auto-refresh", value=st.session_state.auto_refresh)
    st.session_state.auto_refresh = auto_refresh

    if auto_refresh:
        refresh_interval = st.slider("Interval (minutes)", 10, 120, 30)

    st.markdown("---")

    st.subheader("📊 Display Options")

    show_all_jobs = st.checkbox("Show All Jobs", value=True, help="Uncheck to limit display")

    if not show_all_jobs:
        max_display = st.slider("Max Jobs to Display", 20, 500, 200)
    else:
        max_display = None  # Will show all jobs

    filter_keywords = st.text_input("Filter Keywords (comma-separated)", "")

    st.markdown("---")

    st.info("⏱️ Deep scraping takes 2-5 minutes with delays between requests.")

    if st.button("🗑️ Clear All Jobs", type="secondary", use_container_width=True):
        st.session_state.all_jobs = []
        st.session_state.last_update = None
        st.session_state.removed_duplicates = 0
        st.rerun()

# Live indicator
if st.session_state.auto_refresh:
    st.markdown(
        '<div style="text-align: center; margin-bottom: 20px;"><span class="live-indicator"></span> <b>AUTO-REFRESH ACTIVE</b></div>',
        unsafe_allow_html=True)

# Main controls
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    if st.button("🚀 Start Deep Scraping", type="primary", use_container_width=True):
        with st.spinner(f"Deep scraping jobs for {selected_location}..."):
            st.info("⏱️ This will take 2-5 minutes. Please wait...")

            new_jobs, cross_dups = scrape_all_sources(selected_location, [m.lower() for m in work_modes],
                                                      dedup_threshold)

            # Remove duplicates against existing jobs
            combined_jobs = st.session_state.all_jobs + new_jobs
            final_unique_jobs, final_dups = remove_duplicates(combined_jobs, dedup_threshold)

            # Calculate truly new jobs
            truly_new = len(final_unique_jobs) - len(st.session_state.all_jobs)
            total_dups_removed = len(new_jobs) - truly_new + cross_dups + final_dups

            st.session_state.all_jobs = final_unique_jobs
            st.session_state.removed_duplicates += total_dups_removed
            st.session_state.last_update = datetime.now()

            if truly_new > 0:
                st.success(
                    f"✅ Added **{truly_new}** new unique jobs! Removed **{total_dups_removed}** duplicates. Total: **{len(st.session_state.all_jobs)}**")
            else:
                st.warning(f"⚠️ No new unique jobs found. Removed **{total_dups_removed}** duplicates.")

with col2:
    if st.session_state.all_jobs:
        df = pd.DataFrame(st.session_state.all_jobs)
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Export to CSV",
            data=csv,
            file_name=f"it_service_desk_jobs_{selected_location.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )

with col3:
    if st.session_state.last_update:
        time_ago = datetime.now() - st.session_state.last_update
        minutes_ago = int(time_ago.total_seconds() / 60)
        if minutes_ago < 1:
            st.metric("Updated", "Now")
        else:
            st.metric("Updated", f"{minutes_ago}m")

# Statistics
if st.session_state.all_jobs:
    st.markdown("---")
    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

    with col1:
        st.metric("📊 Total", len(st.session_state.all_jobs))

    with col2:
        sources = set([job['source'] for job in st.session_state.all_jobs])
        st.metric("🌐 Sources", len(sources))

    with col3:
        companies = set([job['company'] for job in st.session_state.all_jobs])
        st.metric("🏢 Companies", len(companies))

    with col4:
        remote_jobs = [job for job in st.session_state.all_jobs if 'remote' in job['work_mode'].lower()]
        st.metric("🏠 Remote", len(remote_jobs))

    with col5:
        hybrid_jobs = [job for job in st.session_state.all_jobs if 'hybrid' in job['work_mode'].lower()]
        st.metric("🔀 Hybrid", len(hybrid_jobs))

    with col6:
        today_jobs = [job for job in st.session_state.all_jobs if
                      job['date_posted'] == datetime.now().strftime('%Y-%m-%d')]
        st.metric("📅 Today", len(today_jobs))

    with col7:
        st.metric("🗑️ Removed", st.session_state.removed_duplicates)

# Display jobs
if st.session_state.all_jobs:
    st.markdown("---")
    st.subheader(f"📋 Found {len(st.session_state.all_jobs)} Unique Jobs")

    # Apply filters
    filtered_jobs = st.session_state.all_jobs.copy()

    if filter_keywords:
        keywords = [k.strip().lower() for k in filter_keywords.split(',')]
        filtered_jobs = [
            job for job in filtered_jobs
            if any(keyword in job['title'].lower() or keyword in job['company'].lower()
                   for keyword in keywords)
        ]

    # Source filter
    available_sources = list(set([job['source'] for job in filtered_jobs]))
    selected_sources = st.multiselect(
        "Filter by Source",
        available_sources,
        default=available_sources
    )

    filtered_jobs = [job for job in filtered_jobs if job['source'] in selected_sources]

    # Display filtered count
    if len(filtered_jobs) < len(st.session_state.all_jobs):
        st.info(f"Showing {len(filtered_jobs)} jobs after filtering")

    # Determine how many jobs to display
    jobs_to_display = filtered_jobs if max_display is None else filtered_jobs[:max_display]

    # Display jobs
    for idx, job in enumerate(jobs_to_display):
        with st.expander(f"**{job['title']}** at {job['company']} - {job['work_mode']}", expanded=False):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**🏢 Company:** {job['company']}")
                st.markdown(f"**📍 Location:** {job['location']}")
                st.markdown(f"**💼 Work Mode:** {job['work_mode']}")
                st.markdown(f"**👔 Experience:** {job['experience']}")
                st.markdown(f"**💰 Salary:** {job['salary']}")
                st.markdown(f"**🌐 Source:** {job['source']}")
                st.markdown(f"**📅 Posted:** {job['date_posted']}")
                st.markdown(f"**🕐 Scraped:** {job['scraped_at']}")

            with col2:
                if job['url']:
                    st.link_button("🔗 View Job", job['url'], use_container_width=True)

    # Show message if display is limited
    if max_display is not None and len(filtered_jobs) > max_display:
        st.warning(
            f"⚠️ Showing {max_display} of {len(filtered_jobs)} jobs. Check 'Show All Jobs' in the sidebar to see all results.")

else:
    st.info("👆 Click 'Start Deep Scraping' to begin searching for jobs!")

# Auto-refresh logic
if auto_refresh and st.session_state.last_update:
    time_since_update = (datetime.now() - st.session_state.last_update).total_seconds() / 60

    if time_since_update >= refresh_interval:
        st.info(f"🔄 Auto-refresh triggered after {refresh_interval} minutes...")
        time.sleep(2)
        st.rerun()

# Footer
st.markdown("---")