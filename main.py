import os
import re
from datetime import datetime, timedelta
import asyncio
import pytesseract
from PIL import Image
import requests
from io import BytesIO
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# [1] 전일 마감일 날짜 산출
# ---------------------------------------------------------------------------
def get_yesterday_date():
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d"), yesterday

# ---------------------------------------------------------------------------
# [2] 수집 제외 및 채용규모 판별 로직
# ---------------------------------------------------------------------------
def evaluate_job_posting(job):
    title = job.get("title", "")
    roles = job.get("roles", []) # 직무 리스트
    count = job.get("count", 0)   # 채용 인원 (알 수 없으면 -1)

    # 1. 체험형 인턴 제외
    if "체험형" in title or "체험형 인턴" in title or "체험형인턴" in title:
        return False, None

    # 2. 직무 1개 & 10명 이하 제외
    if len(roles) == 1 and 0 < count <= 10:
        return False, None

    # 3. 채용인원 규모를 알 수 없는 경우 (-1)
    if count == -1:
        is_large_role = any(r in title or r in "".join(roles) for r in ["생산", "제조", "오퍼레이터", "생산직", "조립"])
        if len(roles) >= 4 or is_large_role:
            scale_text = "대규모 채용 추정(직무 4개 이상 또는 생산직무)"
            return True, scale_text
        else:
            return False, None

    # 10명 초과이거나 조건 충족 시
    scale_text = f"약 {count}명" if count > 0 else "대규모 채용 추정"
    return True, scale_text

# ---------------------------------------------------------------------------
# [3] 발표예상시기 산출 로직
# ---------------------------------------------------------------------------
def calculate_announcement_range(text, deadline_dt, doc_pass_dt=None):
    # 1. 필기합격 발표일 직접 명시
    pass_match = re.search(r'필기\s*합격\s*발표[:\s]*(\d{1,2})월\s*(\d{1,2})일', text)
    if pass_match:
        m, d = map(int, pass_match.groups())
        target_date = datetime(deadline_dt.year, m, d)
        return target_date.strftime("%Y-%m-%d")

    # 2. 필기시험/시행일만 있는 경우 (+2일 ~ +7일)
    exam_match = re.search(r'필기\s*(?:시험|시행)[:\s]*(\d{1,2})월\s*(\d{1,2})일', text)
    if exam_match:
        m, d = map(int, exam_match.groups())
        exam_dt = datetime(deadline_dt.year, m, d)
        s_date = exam_dt + timedelta(days=2)
        e_date = exam_dt + timedelta(days=7)
        return f"{s_date.strftime('%Y-%m-%d')} ~ {e_date.strftime('%Y-%m-%d')}"

    # 3. 서류전형 후 바로 면접인 경우
    is_direct_interview = "면접" in text and not re.search(r'(인적성|적성검사|NCS|필기전형|GSAT|SKCT)', text)
    if is_direct_interview:
        if doc_pass_dt: # 서류 합격일 기준 +5일 ~ +10일
            s_date = doc_pass_dt + timedelta(days=5)
            e_date = doc_pass_dt + timedelta(days=10)
        else: # 서류 마감일 기준 +5일 ~ +14일
            s_date = deadline_dt + timedelta(days=5)
            e_date = deadline_dt + timedelta(days=14)
        return f"{s_date.strftime('%Y-%m-%d')} ~ {e_date.strftime('%Y-%m-%d')}"

    # 4. 적성/인적성 검사 포함 전형 (+14일 ~ +24일)
    s_date = deadline_dt + timedelta(days=14)
    e_date = deadline_dt + timedelta(days=24)
    return f"{s_date.strftime('%Y-%m-%d')} ~ {e_date.strftime('%Y-%m-%d')}"

# ---------------------------------------------------------------------------
# [4] OCR 텍스트 추출
# ---------------------------------------------------------------------------
def extract_ocr(image_url):
    try:
        res = requests.get(image_url, timeout=10)
        if res.status_code == 200:
            img = Image.open(BytesIO(res.content))
            return pytesseract.image_to_string(img, lang='kor+eng')
    except Exception:
        pass
    return ""

# ---------------------------------------------------------------------------
# [5] 메인 크롤링 & 데이터 정리
# ---------------------------------------------------------------------------
async def main():
    target_date_str, target_dt = get_yesterday_date()
    site_priority = ["자소설닷컴", "사람인", "잡코리아", "캐치", "링커리어"]

    # 가상 수집 데이터 예시 (실제 브라우저 크롤링 파싱 결과물이 유입되는 구조)
    raw_data = [
        {
            "site": "자소설닷컴",
            "company": "OO전자",
            "title": "2026 하반기 신입 채용공고",
            "roles": ["SW개발", "HW설계", "영업", "생산관리"],
            "count": -1,
            "deadline": target_dt,
            "link": "https://jasoseol.com/recruiting/101",
            "text": "서류전형 -> GSAT 인적성 -> 면접",
            "images": []
        },
        {
            "site": "사람인",
            "company": "OO전자", # 동일 기업/직무 중복 테스트 (자소설닷컴 우선순위에 의해 제외됨)
            "title": "2026 하반기 신입 채용공고",
            "roles": ["SW개발", "HW설계", "영업", "생산관리"],
            "count": -1,
            "deadline": target_dt,
            "link": "https://saramin.co.kr/101",
            "text": "서류전형 -> GSAT 인적성 -> 면접",
            "images": []
        },
        {
            "site": "잡코리아",
            "company": "XX인프라",
            "title": "생산직무 대규모 채용",
            "roles": ["생산직"],
            "count": -1,
            "deadline": target_dt,
            "link": "https://jobkorea.co.kr/202",
            "text": "서류전형 -> 면접전형",
            "images": []
        }
    ]

    # 1. 중복 제거 (기업명 + 직무명 조합 기준 우선순위 적용)
    unique_postings = {}
    for item in raw_data:
        key = f"{item['company']}_{','.join(sorted(item['roles']))}"
        if key not in unique_postings:
            unique_postings[key] = item
        else:
            existing_site = unique_postings[key]["site"]
            if site_priority.index(item["site"]) < site_priority.index(existing_site):
                unique_postings[key] = item

    # 2. 수집 조건 검증 및 출력 텍스트 구성
    output_lines = []
    
    for item in unique_postings.values():
        is_valid, scale_text = evaluate_job_posting(item)
        if not is_valid:
            continue

        combined_text = item["text"]
        for img_url in item["images"]:
            combined_text += "\n" + extract_ocr(img_url)

        announcement_time = calculate_announcement_range(combined_text, item["deadline"])

        # 지정된 메모장 출력 양식
        output_lines.append(f"면접대상자 발표 시기: {announcement_time}")
        output_lines.append(f"기업명: {item['company']}")
        output_lines.append(f"채용공고명: {item['title']}")
        output_lines.append(f"채용규모(예상): {scale_text}")
        output_lines.append(f"채용공고링크: {item['link']}")
        output_lines.append("-" * 40)

    # 3. 메모장 저장
    filename = "announcement_schedule.txt"
    with open(filename, "w", encoding="utf-8") as f:
        if output_lines:
            f.write("\n".join(output_lines))
        else:
            f.write("전일 마감된 수집 대상 채용공고가 없습니다.")

    print("완료: announcement_schedule.txt 저장 성공")

if __name__ == "__main__":
    asyncio.run(main())