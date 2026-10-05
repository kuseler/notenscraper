import difflib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import boto3
import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

BASE_URL = "https://dualis.dhbw.de/scripts/mgrqispi.dll"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8,en-US;q=0.7',
    'Origin': 'https://dualis.dhbw.de',
    'Referer': 'https://dualis.dhbw.de/',
}

# Network timeouts: (connect timeout, read timeout)
REQUEST_TIMEOUT = (5, 15)


def parse_result_details(html: str) -> list:
    """Extrahiert Teilleistungen/Prüfungsergebnisse aus der RESULTDETAILS-Popup-Seite."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', class_='tb')
    if not table:
        return []

    partial_results = []
    current_attempt = ""
    current_unit = ""

    for tr in table.find_all('tr'):
        # Versuch-Ebene (z.B. Versuch 1, Versuch 2)
        td_lvl1 = tr.find('td', class_='level01')
        if td_lvl1 and 'Versuch' in td_lvl1.get_text():
            current_attempt = ' '.join(td_lvl1.get_text().split())
            continue

        # Untereinheit oder Modulabschlussleistung (level02)
        td_lvl2 = tr.find('td', class_='level02')
        if td_lvl2:
            txt = ' '.join(td_lvl2.get_text().split())
            if not 'Gesamt' in txt and txt:
                current_unit = txt
            continue

        # Datenzeile mit Teilleistung
        tbdata_tds = tr.find_all('td', class_='tbdata')
        if len(tbdata_tds) >= 4:
            semester = tbdata_tds[0].get_text(strip=True)
            exam_name = tbdata_tds[1].get_text(strip=True)
            date = tbdata_tds[2].get_text(strip=True)
            grade = tbdata_tds[3].get_text(strip=True)

            status = ""
            for extra_td in tbdata_tds[4:]:
                img = extra_td.find('img')
                if img:
                    status = img.get('alt') or img.get('title') or ""
                    if status:
                        break
                elif extra_td.get_text(strip=True):
                    status = extra_td.get_text(strip=True)
                    break

            if exam_name or grade:
                entry = {
                    "attempt": current_attempt,
                    "unit": current_unit,
                    "exam": exam_name,
                    "semester": semester,
                    "date": date,
                    "grade": grade
                }
                if status:
                    entry["status"] = status
                partial_results.append(entry)

    return partial_results


def scrape_grades() -> dict:
    username = os.environ.get('SCRAPER_USERNAME') or os.environ.get('USER')
    password = os.environ.get('SCRAPER_PASSWORD') or os.environ.get('PASS')

    if not username or not password:
        raise ValueError("SCRAPER_USERNAME (or USER) and SCRAPER_PASSWORD (or PASS) environment variables must be set.")

    payload = {
        'usrname': username,
        'pass': password,
        'APPNAME': 'CampusNet',
        'PRGNAME': 'LOGINCHECK',
        'ARGUMENTS': 'clino,usrname,pass,menuno,menu_type,browser,platform',
        'clino': '000000000000001',
        'menuno': '000324',
        'menu_type': 'classic',
        'browser': '',
        'platform': ''
    }

    with requests.Session() as session:
        # 1. Login
        login_response = session.post(
            BASE_URL,
            headers=HEADERS,
            data=payload,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT
        )
        refresh_header = login_response.headers.get('REFRESH') or login_response.headers.get('refresh', '')
        match = re.search(r'ARGUMENTS=([^,]+)', refresh_header)

        if not match:
            raise RuntimeError(f"Login failed (HTTP {login_response.status_code}). Check your credentials.")

        session_arg = match.group(1)

        # 2. MLSSTART
        mls_url = f"{BASE_URL}?APPNAME=CampusNet&PRGNAME=MLSSTART&ARGUMENTS={session_arg},-N000019,"
        session.get(mls_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

        # 3. STUDENT_RESULT (Leistungsübersicht)
        grades_url = (
            f"{BASE_URL}?APPNAME=CampusNet&PRGNAME=STUDENT_RESULT"
            f"&ARGUMENTS={session_arg},-N000310,-N0,-N000000000000000,-N000000000000000,-N000000000000000,-N0,-N000000000000000"
        )
        grades_response = session.get(grades_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        grades_response.encoding = 'utf-8'

        # 4. Parse Module und Detail-Links
        soup = BeautifulSoup(grades_response.text, 'html.parser')

        modules = []
        detail_urls = {}
        current_category = ""

        for row in soup.find_all('tr'):
            cells = [td.get_text(strip=True) for td in row.find_all('td')]
            if not cells:
                continue

            # Kategorie-Überschrift
            if len(cells) >= 1 and cells[0] and all(c == '' for c in cells[1:]):
                current_category = cells[0]
            # Modulzeile
            elif len(cells) >= 5 and re.match(r'^[A-Z0-9_]{3,}$', cells[0]):
                mod_id = cells[0]
                td_name = row.find_all('td')[1]

                # Popup-URL für Teilleistungen suchen
                link = td_name.find('a')
                if link:
                    onclick = link.get('onclick', '')
                    m = re.search(r"dl_popUp\('([^']+)'", onclick)
                    if m:
                        detail_urls[mod_id] = "https://dualis.dhbw.de" + m.group(1)

                # Status auslesen: bevorzugt img alt/title (z.B. 'Bestanden', 'Offen'), sonst Text
                tds = row.find_all('td')
                status = ""
                if len(tds) > 5:
                    status_img = tds[5].find('img')
                    if status_img:
                        status = status_img.get('alt') or status_img.get('title') or ""
                    if not status:
                        status = tds[5].get_text(strip=True)

                if not status:
                    for td in tds[4:]:
                        img = td.find('img')
                        if img:
                            status = img.get('alt') or img.get('title') or ""
                            if status:
                                break

                modules.append({
                    "id": mod_id,
                    "name": cells[1],
                    "category": current_category,
                    "date": cells[2] if len(cells) > 2 else "",
                    "credits": cells[3] if len(cells) > 3 else "",
                    "grade": cells[4] if len(cells) > 4 else "",
                    "status": status,
                    "partial_results": []
                })

        # 5. Teilleistungen parallel abrufen
        def fetch_detail(item):
            m_id, url = item
            try:
                res = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                res.encoding = 'utf-8'
                return m_id, parse_result_details(res.text)
            except Exception:
                return m_id, []

        with ThreadPoolExecutor(max_workers=5) as executor:
            details_results = dict(executor.map(fetch_detail, detail_urls.items()))

        for mod in modules:
            if mod["id"] in details_results:
                mod["partial_results"] = details_results[mod["id"]]

        # GPA auslesen
        gpa = {}
        for th in soup.find_all('th', class_='tbsubhead'):
            text = th.get_text(strip=True)
            if 'GPA' in text:
                next_th = th.find_next_sibling('th')
                if next_th:
                    key = 'gesamt' if 'Gesamt' in text else 'hauptfach'
                    gpa[key] = next_th.get_text(strip=True)

        # Credits auslesen
        credits_info = {}
        page_text = soup.get_text()
        req_match = re.search(r'Erforderliche Credits[^\d]+([\d,]+)', page_text)
        if req_match:
            credits_info["required"] = req_match.group(1)

        # Non-deterministic fields excluded, deterministic dictionary
        return {
            "credits": credits_info,
            "gpa": gpa,
            "modules": modules
        }


def lambda_handler(event=None, context=None) -> str:
    table_name = os.environ.get('TABLE_NAME')
    if not table_name:
        raise ValueError("TABLE_NAME environment variable is not set.")

    topic_arn = os.environ.get('SNS_TOPIC_ARN')

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    sns = boto3.client('sns')

    # 1. Scrape current data
    scraped_data = scrape_grades()
    current_json = json.dumps(scraped_data, indent=2, sort_keys=True, ensure_ascii=False)

    # 2. Retrieve previous state from DynamoDB
    response = table.get_item(Key={'id': 'latest_report'})
    item = response.get('Item')

    now_iso = datetime.now(timezone.utc).isoformat()

    # Case 1: First run - record initial state
    if not item or 'report' not in item:
        table.put_item(Item={
            'id': 'latest_report',
            'report': current_json,
            'updated_at': now_iso
        })
        return "initial_run_recorded"

    previous_json = item['report']

    # Case 2: Identical content - unchanged
    if previous_json == current_json:
        return "unchanged"

    # Case 3: Diff detected - compute unified diff
    diff_lines = list(difflib.unified_diff(
        previous_json.splitlines(keepends=True),
        current_json.splitlines(keepends=True),
        fromfile='previous_report',
        tofile='current_report',
    ))

    if not diff_lines:
        return "unchanged"

    diff_text = ''.join(diff_lines)

    # Publish diff to SNS
    if topic_arn:
        sns.publish(
            TopicArn=topic_arn,
            Subject='Dualis Notenänderung erkannt!',
            Message=f"Eine Änderung in den Dualis-Noten wurde festgestellt:\n\n{diff_text}"
        )

    # Save updated report to DynamoDB
    table.put_item(Item={
        'id': 'latest_report',
        'report': current_json,
        'updated_at': now_iso
    })

    return "diff_detected"


def main():
    if "TABLE_NAME" in os.environ:
        try:
            result = lambda_handler()
            print(result)
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
            sys.exit(1)
    else:
        try:
            data = scrape_grades()
            print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
