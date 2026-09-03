import os
import re
import requests
import imaplib
import email
from email.header import decode_header
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime
import google.generativeai as genai

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# 수집할 RSS 목록
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
    """'Why?' 중심의 시사점/인사이트 추출 캐러셀 대본 생성"""
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY가 설정되지 않았습니다.")
        return "Gemini API 키가 없습니다."
    
    prompt = f"""
    당신은 트렌드 현상에 대해 "왜 그럴까?(Why?)"라는 화두를 가볍게 던지고, 그 이면에 숨겨진 비즈니스/심리적 인사이트를 재치 있게 짚어주는 인스타그램 인플루언서입니다.

    아래 글을 읽고, 내 계정 컨셉에 맞춘 5장 분량의 카드뉴스 대본을 작성해 주세요.

    [톤앤매너 & 작성 지침]:
    1. 친근하면서도 호기심을 자극하는 말투(~할까요?, ~한 이유)를 사용하세요.
    2. 복잡하고 긴 설명 대신 카드뉴스 이미지에 바로 넣을 수 있게 **단문/불릿포인트(2~3줄 내외)**로 작성하세요.
    3. 단순히 '무슨 일이 일어났다'를 전달하기보다, **'왜 이런 현상이 생겨났는지' 그 이면의 숨은 원인과 인사이트**에 집중하세요.

    [글 제목]: {title}
    [글 내용]: {content_text[:1500]}

    [출력 양식]:
    [1장 - 커버 (Question)]
    제목: (Why? 화두를 던지는 호기심 유발 질문 1문장)
    부제목: (현상을 한 줄로 나타내는 호기심 훅)

    [2장 - 현상 (What)]
    • (요즘 눈에 띄는 현상/사례 가볍게 소개 1)
    • (현상/사례 포인트 2)

    [3장 - 이면의 원인 (Why?)]
    • Why 1: (표면 뒤에 숨겨진 소비자 심리나 의도)
    • Why 2: (기업/마케터가 노린 핵심 전략)

    [4장 - 시사점 (So What?)]
    • (이 현상에서 우리가 건질 만한 가벼운 인사이트 1)
    • (기획자/마케터가 적용해 볼 점 2)

    [5장 - 마무리 (Your Turn)]
    • 한 줄 정리: (전체 관점을 밝히는 재치 있는 한 줄)
    • 질문: (독자들에게 '여러분의 생각은 어떤가요?' 묻는 질문)
    """

    genai.configure(api_key=GEMINI_API_KEY)
    models_to_try = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.1-pro"
    ]

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"⚠️ Gemini 모델 시도 실패 ({model_name}): {e}")

    return "대본 생성 실패 (모든 Gemini 모델 응답 불가)"

def fetch_wepick_articles():
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
            
            for post_url in post_links[:5]:
                try:
                    p_res = requests.get(post_url, headers=headers, timeout=10)
                    if p_res.status_code == 200:
                        p_soup = BeautifulSoup(p_res.text, "html.parser")
                        
                        title_el = p_soup.find("h1") or p_soup.find("title")
                        title = title_el.get_text(strip=True) if title_el else "위픽레터 아티클"
                        title = re.sub(r' - 위픽레터.*$', '', title)
                        
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
        
        status, messages = mail.search('utf-8', 'X-GM-RAW', '"label:뉴스레터 is:unread"')
        
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
    """대본을 데이터베이스 표 속성이 아닌 노션 '페이지 본문' 블록으로 추가"""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    today = datetime.now().strftime("%Y-%m-%d")
    
    children_blocks = []
    lines = carousel_script.strip().split('\n')
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        if line_str.startswith('[') and line_str.endswith(']'):
            children_blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line_str}}]
                }
            })
        elif line_str.startswith('•') or line_str.startswith('-'):
            clean_content = line_str.lstrip('•- ').strip()
            children_blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": clean_content}}]
                }
            })
        else:
            children_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line_str}}]
                }
            })

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "트렌드명": {"title": [{"text": {"content": item["title"]}}]},
            "출처": {"select": {"name": item["source"]}},
            "키워드": {"multi_select": [{"name": "뉴스레터"}]},
            "트렌드 점수": {"number": 95},
            "상태": {"status": {"name": "시작 전"}},
            "링크": {"url": item["link"]},
            "날짜": {"date": {"start": today}}
        },
        "children": children_blocks
    }
    requests.post(url, headers=headers, json=payload)

def main():
    existing_urls = get_existing_urls()
    print(f"📌 기존 저장된 링크 수: {len(existing_urls)}개")
    
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
