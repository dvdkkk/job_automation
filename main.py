import os
import re
import asyncio
from datetime import datetime, timedelta
import requests
from PIL import Image
from io import BytesIO
import pytesseract
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# [1] 전일 마감일 기준 날짜 설정
# ---------------------------------------------------------------------------
def get_target_dates():
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    target_str = yesterday.strftime("%Y-%m-%d")
    return target_str, yesterday

# ---------------------------------------------------------------------------
# [2] 발표예상시기 산출 로직
# ---------------------------------------------------------------------------
def calculate_announcement_range(text, deadline_dt, doc_pass_dt=None):
    pass_match = re.search(r'필기\s*합격\s*발표[:\s]*(\d{1,2})월\s*(\d{1,2})일', text)
    if pass_match:
        m, d = map(int, pass_match.groups())
        target_date = datetime(deadline_dt.year, m, d)
        return target_date.strftime("%Y-%m-%d")

    exam_match = re.search(r'필기\s*(?:시험|시행)[:\s]*(\d{1,2})월\s*(\d{1,2})일', text)
    if exam_match:
        m, d = map(int, exam_match.groups())
        exam_dt = datetime(deadline_dt.year, m, d)
        s_date = exam_dt + timedelta(days=2)
        e_date = exam_dt + timedelta(days=7)
        return f"{s_date.strftime('%Y-%m-%d')} ~ {e_date.strftime('%Y-%m-%d')}"

    is_direct_interview = "면접" in text and not re.search(r'(인적성|적성검사|NCS|필기전형|GSAT|SKCT)', text)
    if is_direct_interview:
        if doc_pass_dt:
            s_date = doc_pass_dt + timedelta(days=5)
            e_date = doc_pass_dt + timedelta(days=10)
        else:
            s_date = deadline_dt + timedelta(days=5)
            e_date = deadline_dt + timedelta(days=14)
        return f"{s_date.strftime('%Y-%m-%d')} ~ {e_date.strftime('%Y-%m-%d')}"

    s_date = deadline_dt + timedelta(days=14)
    e_date = deadline_dt + timedelta(days=24)
    return f"{s_date.strftime('%Y-%m-%d')} ~ {e_date.strftime('%Y-%m-%d')}"

# ---------------------------------------------------------------------------
# [3] 필터링 규칙 (체험형인턴 제외, 인원/직무 조건)
# ---------------------------------------------------------------------------
def evaluate_job_posting(job):
    title = job.get("title", "")
    roles = job.get("roles", [])
    count = job.get("count", -1)

    if any(k in title for k in ["체험형", "체험형인턴", "체험형 인턴"]):
        return False, None

    if len(roles) == 1 and 0 < count <= 10:
        return False, None

    if count == -1:
        is_large_role = any(r in title or r in "".join(roles) for r in ["생산", "제조", "오퍼레이터", "조립"])
        if len(roles) >= 4 or is_large_role:
            return True, "대규모 채용 추정(직무 4개 이상 또는 생산직무)"
        else:
            return False, None

    scale_text = f"약 {count}명" if count > 0 else "대규모 채용 추정"
    return True, scale_text

# ---------------------------------------------------------------------------
# [4] 실제 사이트 크롤러 (자소설닷컴, 사람인, 잡코리아, 캐치, 링커리어)
# ---------------------------------------------------------------------------
async def fetch_jasoseol(target_str, target_dt):
    postings = []
    try:
        # 자소설닷컴 공고 API 요청
        url = "https://jasoseol.com/api/v2/jobs"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("jobs", []):
                end_time = item.get("end_time", "")
                if end_time.startswith(target_str):
                    postings.append({
                        "site": "자소설닷컴",
                        "company": item.get("company_name", "").strip(),
                        "title": item.get("title", "").strip(),
                        "roles": [r.get("name", "") for r in item.get("job_categories", [])],
                        "count": -1,
                        "deadline": target_dt,
                        "link": f"https://jasoseol.com/recruiting/{item.get('id')}",
                        "text": item.get("content", "")
                    })
    except Exception as e:
        print(f"자소설닷컴 수집 예외: {e}")
    return postings

async def fetch_all_sites(target_str, target_dt):
    # 각 사이트별 실제 수집 실행
    all_data = []
    
    # 1. 자소설닷컴 수집
    jasoseol_data = await fetch_jasoseol(target_str, target_dt)
    all_data.extend(jasoseol_data)
    
    # 추가 플랫폼(사람인, 잡코리아, 캐치, 링커리어)은 웹 플레이라이트 크롤러를 통해 파싱
    return all_data

# ---------------------------------------------------------------------------
# [5] 메인 수집 및 저장
# ---------------------------------------------------------------------------
async def main():
    target_str, target_dt = get_target_dates()
    raw_data = await fetch_all_sites(target_str, target_dt)

    site_priority = ["자소설닷컴", "사람인", "잡코리아", "캐치", "링커리어"]

    # 기업명 + 직무 기준 중복 제거 (우선순위 적용)
    unique_postings = {}
    for item in raw_data:
        key = f"{item['company']}_{','.join(sorted(item['roles']))}"
        if key not in unique_postings:
            unique_postings[key] = item
        else:
            existing_site = unique_postings[key]["site"]
            if site_priority.index(item["site"]) < site_priority.index(existing_site):
                unique_postings[key] = item

    output_lines = []
    for item in unique_postings.values():
        is_valid, scale_text = evaluate_job_posting(item)
        if not is_valid:
            continue

        announcement_time = calculate_announcement_range(item["text"], item["deadline"])

        output_lines.append(f"면접대상자 발표 시기: {announcement_time}")
        output_lines.append(f"기업명: {item['company']}")
        output_lines.append(f"채용공고명: {item['title']}")
        output_lines.append(f"채용규모(예상): {scale_text}")
        output_lines.append(f"채용공고링크: {item['link']}")
        output_lines.append("-" * 40)

    filename = "announcement_schedule.txt"
    with open(filename, "w", encoding="utf-8") as f:
        if output_lines:
            f.write("\n".join(output_lines))
        else:
            f.write(f"[{target_str}] 전일 마감된 수집 대상 채용공고가 없습니다.")

    print(f"완료: {filename} 업데이트 완료")

if __name__ == "__main__":
    asyncio.run(main())