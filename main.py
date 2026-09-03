import os
import re
import requests
import imaplib
import email
from email.header import decode_header
import xml.etree.ElementTree as ET
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# 수집할 RSS 및 스티비 아카이브 목록
RSS_FEEDS = [
    {"name": "스티비 아카이브", "url": "https://page.stibee.com/rss/archives/325254"},
    {"name": "뉴닉", "url": "https://www.newneek.co/rss"},
    {"name": "고구마팜", "url": "https://gogumafarm.kr/feed/"},
    {"name": "마케팅/트렌드 뉴스", "url": "https://news.google.com/rss/search?q=플랫폼+서비스+OR+Z세대+트렌드+OR+마케팅+사례+OR+팝업스토어&hl=ko&gl=KR&ceid=KR:ko"}
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
    if not OPENAI_API_KEY:
        print("⚠️ OPENAI_API_KEY가 없습니다.")
        return "OpenAI API 키가 설정되지 않았습니다."
    
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
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
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "너는 트렌드/마케팅 캐러셀 카드뉴스 전문 에디터야."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    res = requests.post(url, headers=headers, json=payload)
    if res.status_code == 200:
        return res.json()["choices"][0]["message"]["content"].strip()
    else:
        print(f"⚠️ OpenAI 오류: {res.status_code} - {res.text}")
        return f"대본 생성 실패 ({res.status_code})"

def fetch_rss_items():
    items = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for feed in RSS_FEEDS:
        try:
            res = requests.get(feed["url"], headers=headers, timeout=10)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall(".//item")[:2]:
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
        
        status, _ = mail.select('"뉴스레터"')
        if status != 'OK':
            mail.select('INBOX')
            
        status, messages = mail.search(None, 'UNSEEN')
        if status != 'OK' or not messages[0]:
            return []

        email_ids = messages[0].split()
        for e_id in email_ids[-3:]:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                    
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
    
    all_items = fetch_rss_items() + fetch_gmail_newsletters()
    new_count = 0
    
    for item in all_items:
        if item["link"] not in existing_urls:
            existing_urls.add(item["link"])
            print(f"🤖 캐러셀 대본 생성 중: {item['title']}")
            script = generate_carousel_script(item["title"], item["description"])
            
            send_to_notion(item, script)
            new_count += 1
            print(f"✅ 노션 전송 완료: {item['title']}")
            
    print(f"🎉 총 {new_count}개의 새로운 캐러셀 대본이 추가되었습니다.")

if __name__ == "__main__":
    main()
