import os
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# 💡 원하는 키워드로 수정하세요
KEYWORDS = ["생성형 AI", "플랫폼 서비스", "스타트업 트렌드", "Z세대 트렌드", "숏폼 마케팅"]

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
    seen_urls = set()
    for kw in KEYWORDS:
        data = fetch_youtube(kw) + fetch_rss(kw)
        for item in data:
            if item["link"] not in seen_urls:
                seen_urls.add(item["link"])
                send_to_notion(item)

if __name__ == "__main__":
    main()
