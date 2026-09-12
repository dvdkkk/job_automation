import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# 1. 날짜 설정 (어제 마감된 공고만 필터링)
today = datetime.now()
yesterday = today - timedelta(days=1)

# 검색용 날짜 포맷 생성
yesterday_m_d_1 = yesterday.strftime("%m/%d")         # 예: "09/11"
yesterday_m_d_2 = f"{yesterday.month}/{yesterday.day}" # 예: "9/11"
yesterday_kor = f"{yesterday.month}월 {yesterday.day}일" # 예: "9월 11일"

print(f"=== [수집 기준일] 어제 마감된 공고: {yesterday.strftime('%Y-%m-%d')} ===")

# 2. 발표 일정 계산 함수 (규칙: 서류 마감일 기준 5~10일 뒤)
def calculate_announcement_dates(deadline_dt):
    start_date = deadline_dt + timedelta(days=5)
    end_date = deadline_dt + timedelta(days=10)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

# 어제 마감일 여부 확인 함수
def is_yesterday_deadline(text):
    if not text:
        return False
    targets = [yesterday_m_d_1, yesterday_m_d_2, yesterday_kor, "어제마감", "어제 마감"]
    return any(target in text for target in targets)

# --- 1) 사람인 ---
async def scrape_saramin(page):
    results = []
    try:
        url = "https://www.saramin.co.kr/zf_user/search/recruit?search_area=main&search_done=y&searchType=search&searchword=%EC%B1%84%EC%9A%A9&sort=date"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        items = soup.select('.item_recruit')
        
        for item in items:
            date_info = item.select_one('.badge_date') or item.select_one('.date')
            date_text = date_info.text.strip() if date_info else ""
            
            if is_yesterday_deadline(date_text):
                title_elem = item.select_one('.job_tit a')
                corp_elem = item.select_one('.corp_name a')
                if title_elem and corp_elem:
                    title = title_elem.text.strip()
                    corp = corp_elem.text.strip()
                    href = title_elem.get('href', '')
                    link = "https://www.saramin.co.kr" + href if href.startswith('/') else href
                    
                    start_p, end_p = calculate_announcement_dates(yesterday)
                    results.append({'corp': corp, 'title': title, 'link': link, 'start_p': start_p, 'end_p': end_p, 'site': '사람인'})
    except Exception as e:
        print(f"[사람인] 수집 중 예외 발생: {e}")
    return results

# --- 2) 잡코리아 ---
async def scrape_jobkorea(page):
    results = []
    try:
        url = "https://www.jobkorea.co.kr/Search/?stext=%EC%B1%84%EC%9A%A9&tabType=corp&Page_No=1"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        items = soup.select('.list-post')
        
        for item in items:
            date_info = item.select_one('.option .date')
            date_text = date_info.text.strip() if date_info else ""
            
            if is_yesterday_deadline(date_text):
                title_elem = item.select_one('.title')
                corp_elem = item.select_one('.name')
                if title_elem and corp_elem:
                    title = title_elem.text.strip()
                    corp = corp_elem.text.strip()
                    href = title_elem.get('href', '')
                    link = "https://www.jobkorea.co.kr" + href if href.startswith('/') else href
                    
                    start_p, end_p = calculate_announcement_dates(yesterday)
                    results.append({'corp': corp, 'title': title, 'link': link, 'start_p': start_p, 'end_p': end_p, 'site': '잡코리아'})
    except Exception as e:
        print(f"[잡코리아] 수집 중 예외 발생: {e}")
    return results

# --- 3) 캐치 ---
async def scrape_catch(page):
    results = []
    try:
        url = "https://www.catch.co.kr/NCS/Recruit"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        items = soup.select('.recruit_list li') or soup.select('tbody tr')
        
        for item in items:
            date_info = item.select_one('.date') or item.select_one('.dday')
            date_text = date_info.text.strip() if date_info else ""
            
            if is_yesterday_deadline(date_text):
                title_elem = item.select_one('.title') or item.select_one('.name a')
                corp_elem = item.select_one('.corp') or item.select_one('.comp')
                if title_elem and corp_elem:
                    title = title_elem.text.strip()
                    corp = corp_elem.text.strip()
                    href = title_elem.get('href', '')
                    link = "https://www.catch.co.kr" + href if href.startswith('/') else href
                    
                    start_p, end_p = calculate_announcement_dates(yesterday)
                    results.append({'corp': corp, 'title': title, 'link': link, 'start_p': start_p, 'end_p': end_p, 'site': '캐치'})
    except Exception as e:
        print(f"[캐치] 수집 중 예외 발생: {e}")
    return results

# --- 4) 링커리어 ---
async def scrape_linkareer(page):
    results = []
    try:
        url = "https://linkareer.com/list/reception?filterType=JOB&sort=CREATED_AT&order=DESC"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        items = soup.select('article') or soup.select('.recruit-item')
        
        for item in items:
            date_info = item.select_one('.date') or item.select_one('span')
            date_text = date_info.text.strip() if date_info else ""
            
            if is_yesterday_deadline(date_text):
                title_elem = item.select_one('h5') or item.select_one('.title')
                corp_elem = item.select_one('.company-name') or item.select_one('.organization')
                link_elem = item.select_one('a')
                if title_elem and corp_elem and link_elem:
                    title = title_elem.text.strip()
                    corp = corp_elem.text.strip()
                    href = link_elem.get('href', '')
                    link = "https://linkareer.com" + href if href.startswith('/') else href
                    
                    start_p, end_p = calculate_announcement_dates(yesterday)
                    results.append({'corp': corp, 'title': title, 'link': link, 'start_p': start_p, 'end_p': end_p, 'site': '링커리어'})
    except Exception as e:
        print(f"[링커리어] 수집 중 예외 발생: {e}")
    return results

# --- 5) 자소설닷컴 ---
async def scrape_jasoseol(page):
    results = []
    try:
        url = "https://jasoseol.com/"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        items = soup.select('.employment-item') or soup.select('.item-container')
        
        for item in items:
            date_info = item.select_one('.end-time') or item.select_one('.d-day')
            date_text = date_info.text.strip() if date_info else ""
            
            if is_yesterday_deadline(date_text):
                title_elem = item.select_one('.title')
                corp_elem = item.select_one('.company-name')
                link_elem = item.select_one('a')
                if title_elem and corp_elem and link_elem:
                    title = title_elem.text.strip()
                    corp = corp_elem.text.strip()
                    href = link_elem.get('href', '')
                    link = "https://jasoseol.com" + href if href.startswith('/') else href
                    
                    start_p, end_p = calculate_announcement_dates(yesterday)
                    results.append({'corp': corp, 'title': title, 'link': link, 'start_p': start_p, 'end_p': end_p, 'site': '자소설닷컴'})
    except Exception as e:
        print(f"[자소설닷컴] 수집 중 예외 발생: {e}")
    return results

# --- 메인 실행 함수 ---
async def main():
    async with async_playwright() as p:
        # PC 브라우저 위장 설정 (차단 방지)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        all_results = []
        
        print("1. 사람인 수집 중...")
        all_results.extend(await scrape_saramin(page))
        
        print("2. 잡코리아 수집 중...")
        all_results.extend(await scrape_jobkorea(page))
        
        print("3. 캐치 수집 중...")
        all_results.extend(await scrape_catch(page))
        
        print("4. 링커리어 수집 중...")
        all_results.extend(await scrape_linkareer(page))
        
        print("5. 자소설닷컴 수집 중...")
        all_results.extend(await scrape_jasoseol(page))
        
        await browser.close()
        
        # 파일 저장
        output_filename = "announcement_schedule.txt"
        with open(output_filename, "w", encoding="utf-8") as f:
            if not all_results:
                f.write(f"어제({yesterday.strftime('%Y-%m-%d')}) 마감된 수집 대상 채용 공고가 없습니다.\n")
            else:
                for res in all_results:
                    f.write(f"면접대상자 발표 시기: {res['start_p']} ~ {res['end_p']}\n")
                    f.write(f"기업명: {res['corp']}\n")
                    f.write(f"채용공고명: {res['title']}\n")
                    f.write(f"출처: {res['site']}\n")
                    f.write(f"채용공고링크: {res['link']}\n")
                    f.write("-" * 40 + "\n")
                    
        print(f"=== 수집 완료: 총 {len(all_results)}건 저장됨 ===")

if __name__ == "__main__":
    asyncio.run(main())