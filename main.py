import os
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

KEYWORDS = ["생성형 AI", "플랫폼 서비스", "스타트업 트렌드", "Z세대 트렌드", "숏폼 마케팅"]

# 1. 노션 DB에 이미 저장되어 있는 링크 목록 불러오기
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

def fetch_youtube(keyword):
    if not YOUTUBE_API_KEY: 
        return []
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={keyword}&type=video&order=date&maxResults=3&key={YOUTUBE_API_KEY}"
    res = requests.get(url)
    items = []
    if res.status_code == 200:
        for item in res.json().get("items", []):
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            items.append({
                "title": snippet["title"],
                "link": f"https://www.youtube.com/watch?v={video_id}",
                "source": "YouTube",
                "keyword": keyword,
                "score": 85
            })
    return items

def fetch_rss(keyword):
    url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
    res = requests.get(url)
    items = []
    if res.status_code == 200:
        root = ET.fromstring(res.content)
        for item in root.findall(".//item")[:3]:
            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            clean_title = re.sub(r' - [^-]+$', '', title)
            items.append({
                "title": clean_title,
                "link": link,
                "source": "RSS",
                "keyword": keyword,
                "score": 70
            })
    return items

def send_to_notion(item):
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
            "키워드": {"multi_select": [{"name": item["keyword"]}]},
            "트렌드 점수": {"number": item["score"]},
            "상태": {"status": {"name": "시작 전"}},
            "링크": {"url": item["link"]},
            "날짜": {"date": {"start": today}}
        }
    }
    requests.post(url, headers=headers, json=payload)

def main():
    existing_urls = get_existing_urls()
    print(f"📌 현재 노션 DB에 존재하는 기존 데이터 수: {len(existing_urls)}개")
    
    new_count = 0
    for kw in KEYWORDS:
        data = fetch_youtube(kw) + fetch_rss(kw)
        for item in data:
            if item["link"] not in existing_urls:
                existing_urls.add(item["link"])
                send_to_notion(item)
                new_count += 1
                print(f"✅ 새 트렌드 추가됨: {item['title']}")
                
    print(f"🎉 총 {new_count}개의 새로운 트렌드가 추가되었습니다.")

if __name__ == "__main__":
    main()
