import os
import re
import requests
import imaplib
import email
from email.header import decode_header
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# 1. 수집할 RSS 목록
RSS_FEEDS = [
    {"name": "고구마팜", "url": "https://gogumafarm.kr/feed/", "limit": 7},
    {"name": "뉴닉", "url": "https://www.newneek.co/rss", "limit": 7},
    {"name": "스티비 아카이브", "url": "https://page.stibee.com/rss/archives/325254", "limit": 7},
    {"name": "마케팅/트렌드 뉴스", "url": "https://news.google.com/rss/search?q=플랫폼+서비스+OR+Z세대+트렌드+OR+마케팅+사례+OR+팝업스토어&hl=ko&gl=KR&ceid=KR:ko", "limit": 2}
]

def get_existing_urls():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28"
    }
    existing_urls = set()
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            data = res.json()
            for page in data.get("results", []):
                link_prop = page.get("properties", {}).get("링크", {}).get("url")
                if link_prop:
                    existing_urls.add(link_prop)
            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")
        else:
            break
    return existing_urls

def generate_carousel_script(title, content_text):
    """Google Gemini API (gemini-2.0-flash 및 폴백 적용)"""
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY가 설정되지 않았습니다.")
        return "Gemini API 키가 없습니다."
    
    model_urls = [
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
    ]
    
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
    당신은 인스타그램 트렌드/마케팅 캐러셀(카드뉴스) 전문 기획자입니다.
    아래 뉴스레터 글을 바탕으로 5장 분량의 인스타그램 캐러셀 슬라이드 대본을 작성해 주세요.

    [글 제목]: {title}
    [글 내용/요약]: {content_text[:1500]}

    [출력 양식]:
    [1장 - 커버]
    - 헤드카피 (이목을 끄는 강력한 훅):
    - 서브카피:

    [2장 - 배경/현상]
    - 핵심 이슈 요약 (2-3문장):

    [3장 - 핵심 사례 및 특징]
    - 핵심 포인트 및 브랜드 사례 분석:

    [4장 - 마케터/기획자 시사점]
    - 이 트렌드에서 얻을 수 있는 액션 플랜 2가지:

    [5장 - 요약 및 질문]
    - 한 줄 요약:
    - 댓글 유도 질문:
    """

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    for base_url in model_urls:
        endpoint = f"{base_url}?key={GEMINI_API_KEY}"
        try:
            res = requests.post(endpoint, headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                print(f"⚠️ Gemini 모델 시도 실패 ({base_url.split('/')[-1]}): {res.status_code}")
        except Exception as e:
            print(f"⚠️ Gemini 통신 에러: {e}")
            
    return "대본 생성 실패 (모든 Gemini 모델 응답 불가)"

def fetch_wepick_articles():
    """위픽레터(letter.wepick.kr/latest) 아티클 직접 크롤링 수집"""
    items = []
    url = "https://letter.wepick.kr/latest"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            post_links = []
            
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/post/" in href:
                    full_url = href if href.startswith("http") else f"https://letter.wepick.kr{href}"
                    if full_url not in post_links:
                        post_links.append(full_url)
            
            for post_url in post_links[:5]:  # 최신 아티클 5개 수집
                try:
                    p_res = requests.get(post_url, headers=headers, timeout=10)
                    if p_res.status_code == 200:
                        p_soup = BeautifulSoup(p_res.text, "html.parser")
                        
                        # 제목 추출
                        title_el = p_soup.find("h1") or p_soup.find("title")
                        title = title_el.get_text(strip=True) if title_el else "위픽레터 아티클"
                        title = re.sub(r' - 위픽레터.*$', '', title)
                        
                        # 본문 내용 추출
                        clean_text = p_soup.get_text(separator=" ", strip=True)
                        clean_text = re.sub(r'\s+', ' ', clean_text)
                        
                        items.append({
                            "title": title,
                            "link": post_url,
                            "source": "위픽레터",
                            "description": clean_text[:2000]
                        })
                except Exception as e:
                    print(f"위픽레터 아티클 수집 오류 ({post_url}): {e}")
    except Exception as e:
        print(f"위픽레터 크롤링 오류: {e}")
        
    return items

def fetch_rss_items():
    items = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for feed in RSS_FEEDS:
        try:
            res = requests.get(feed["url"], headers=headers, timeout=10)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                fetch_limit = feed.get("limit", 5)
                for item in root.findall(".//item")[:fetch_limit]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    desc = item.find("description").text if item.find("description") is not None else ""
                    
                    clean_desc = re.sub(r'<[^>]+>', '', desc)
                    clean_title = re.sub(r' - [^-]+$', '', title)
                    
                    items.append({
                        "title": clean_title,
                        "link": link,
                        "source": feed["name"],
                        "description": clean_desc
                    })
        except Exception as e:
            print(f"Error fetching {feed['name']}: {e}")
    return items

def fetch_gmail_newsletters():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return []

    items = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select('INBOX')
        
        raw_query = 'label:뉴스레터 is:unread'.encode('utf-8')
        status, messages = mail.search('utf-8', 'X-GM-RAW', raw_query)
        
        if status != 'OK' or not messages[0]:
            print("📬 새 지메일 뉴스레터가 없습니다.")
            mail.logout()
            return []

        email_ids = messages[0].split()
        for e_id in email_ids[-5:]:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject_header = msg["Subject"]
                    subject = "제목 없음"
                    if subject_header:
                        decoded_parts = decode_header(subject_header)
                        sub_list = []
                        for sub_bytes, encoding in decoded_parts:
                            if isinstance(sub_bytes, bytes):
                                sub_list.append(sub_bytes.decode(encoding if encoding else "utf-8", errors="ignore"))
                            elif isinstance(sub_bytes, str):
                                sub_list.append(sub_bytes)
                        subject = "".join(sub_list)
                    
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type in ["text/plain", "text/html"]:
                                try:
                                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                    break
                                except:
                                    pass
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                    
                    clean_body = re.sub(r'<[^>]+>', '', body)
                    clean_body = re.sub(r'\s+', ' ', clean_body).strip()
                    
                    msg_id = msg.get("Message-ID", f"email_{e_id.decode()}")
                    fake_link = f"https://mail.google.com/mail/#search/{msg_id}"
                    
                    items.append({
                        "title": subject,
                        "link": fake_link,
                        "source": "지메일 뉴스레터",
                        "description": clean_body[:2000]
                    })
        mail.logout()
    except Exception as e:
        print(f"지메일 수집 오류: {e}")
        
    return items

def send_to_notion(item, carousel_script):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    today = datetime.now().strftime("%Y-%m-%d")
    
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "트렌드명": {"title": [{"text": {"content": item["title"]}}]},
            "출처": {"select": {"name": item["source"]}},
            "키워드": {"multi_select": [{"name": "뉴스레터"}]},
            "트렌드 점수": {"number": 95},
            "상태": {"status": {"name": "시작 전"}},
            "링크": {"url": item["link"]},
            "날짜": {"date": {"start": today}},
            "캐러셀 대본": {"rich_text": [{"text": {"content": carousel_script[:2000]}}]}
        }
    }
    requests.post(url, headers=headers, json=payload)

def main():
    existing_urls = get_existing_urls()
    print(f"📌 기존 저장된 링크 수: {len(existing_urls)}개")
    
    # RSS + 위픽레터 웹 크롤링 + 지메일 수집통합
    all_items = fetch_rss_items() + fetch_wepick_articles() + fetch_gmail_newsletters()
    new_count = 0
    
    for item in all_items:
        if item["link"] not in existing_urls:
            existing_urls.add(item["link"])
            print(f"🤖 캐러셀 대본 생성 중 (Gemini): {item['title']}")
            script = generate_carousel_script(item["title"], item["description"])
            
            send_to_notion(item, script)
            new_count += 1
            print(f"✅ 노션 전송 완료: {item['title']}")
            
    print(f"🎉 총 {new_count}개의 새로운 캐러셀 대본이 추가되었습니다.")

if __name__ == "__main__":
    main()
