import datetime
import json
import os
import re
import sys
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
TWILIO_MESSAGE_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}.json"
TWILIO_MAX_BODY_LENGTH = 1500
TWILIO_STATUS_CHECK_ATTEMPTS = 3
TWILIO_STATUS_CHECK_DELAY_SECONDS = 2
MAX_FETCH_ATTEMPTS = 2
DEBUG_RESPONSE_DIR = "debug_responses"

TODAY = datetime.datetime.now()
YESTERDAY = TODAY - datetime.timedelta(days=1)


def format_date(dt: datetime.datetime) -> str:
    return dt.strftime("%a, %b %d, %I:%M %p")


# ---------------------------------------------------------------------------
# STRATEGY A: Person tracking (Vaibhav & Hubert)
# We pin EXACT handles/URLs so the model has no freedom to wander.
# ---------------------------------------------------------------------------

HUBERT_SOURCES = {

    "medium": "https://databrickster.medium.com/",
    'youtube_channel': "https://www.youtube.com/@databricks_hubert_dudek",
}

VAIBHAV_SOURCES = {
    "youtube_channel": "https://www.youtube.com/@vaibhavsisinty",  
    "youtube_search": "https://www.youtube.com/results?search_query=Vaibhav+Sisinty+AI",
    "instagram": "https://www.instagram.com/vaibhavsisinty/",         
}

# ---------------------------------------------------------------------------
# STRATEGY B: Topic tracking (Databricks, Spark, Data Engineering, AI)
# We pin OFFICIAL authoritative sources only — no broad web search.
# If the official blog posts it, the rest of the internet echoes it anyway.
# ---------------------------------------------------------------------------

DATABRICKS_SOURCES = [
    # Official blogs
    "https://www.databricks.com/blog",
    "https://www.databricks.com/blog/category/engineering",
    # GitHub releases (authoritative for version bumps)
    "https://github.com/apache/spark/releases",
    "https://github.com/delta-io/delta/releases",
    "https://github.com/databricks/mlflow/releases",
    "https://github.com/unitycatalog/unitycatalog/releases",
    # Community
    "https://community.databricks.com/",
]

DATA_ENGINEERING_SOURCES = [
    # Official project pages / blogs
    "https://www.getdbt.com/blog",
    "https://iceberg.apache.org/releases/",
    "https://github.com/apache/iceberg/releases",
    "https://github.com/apache/airflow/releases",
    "https://flink.apache.org/news/",
    "https://kafka.apache.org/blog",
    "https://github.com/apache/kafka/releases",
    # Cloud platforms (official engineering blogs only)
    "https://cloud.google.com/blog/products/data-analytics",
    "https://aws.amazon.com/blogs/big-data/",
    "https://techcommunity.microsoft.com/category/azure-synapse-analytics/blog/azuresynapseanalyticsblog",
]

AI_SOURCES = [
    # Official lab blogs
    "https://openai.com/blog",
    "https://www.anthropic.com/news",
    "https://deepmind.google/discover/blog/",
    "https://ai.meta.com/blog/",
    "https://mistral.ai/news/",
    "https://cohere.com/blog",
    # GitHub model releases
    "https://github.com/openai/openai-python/releases",
    "https://github.com/anthropics/anthropic-sdk-python/releases",
    "https://huggingface.co/blog",
]


def build_categories() -> List[Dict[str, Any]]:
    hubert_urls = "\n".join(f"- {url}" for url in HUBERT_SOURCES.values())
    vaibhav_urls = "\n".join(f"- {url}" for url in VAIBHAV_SOURCES.values())
    databricks_urls = "\n".join(f"- {url}" for url in DATABRICKS_SOURCES)
    dataeng_urls = "\n".join(f"- {url}" for url in DATA_ENGINEERING_SOURCES)
    ai_urls = "\n".join(f"- {url}" for url in AI_SOURCES)

    return [
        # ---------------------------------------------------------------
        # DATABRICKS & SPARK — pin official sources, no open web search
        # ---------------------------------------------------------------
        {
            "id": "databricks",
            "label": "Databricks & Spark",
            "prompt": (
                f"You are a tech news extractor. Your job is ONLY to extract news from the specific URLs listed below. "
                f"Do NOT search the broader web. Do NOT invent or hallucinate URLs.\n\n"
                f"ONLY look at these official sources:\n{databricks_urls}\n\n"
                f"Find content published in the last 24 hours "
                f"(from {format_date(YESTERDAY)} to {format_date(TODAY)}).\n"
                f"If nothing in 24h, Just return an empty result.\n\n"
                f"Return ONLY a raw JSON array (no markdown, no code fences, no explanation):\n"
                f'[{{"title":"...","summary":"1-2 sentence summary of what happened and why it matters",'
                f'"url":"exact URL from the sources above","source":"e.g. Databricks Blog / Apache Spark GitHub",'
                f'"importance":"high"}}]\n\n'
                f"Rules:\n"
                f"- Maximum 4 items\n"
                f"- Only include items you actually found at those URLs\n"
                f"- Never fabricate a URL; use the exact link from the source page\n"
                f"- Return [] only if the pages are unreachable or truly have no recent content"
            ),
        },

        # ---------------------------------------------------------------
        # HUBERT DUDEK - exact public pages, no open web search
        # ---------------------------------------------------------------
        {
            "id": "hubert",
            "label": "Hubert Dudek",
            "prompt": (
                f"You are a content tracker for a specific person. "
                f"Check ONLY these exact pages for Hubert Dudek's latest posts:\n{hubert_urls}\n\n"
                f"Look for posts, articles, or activity published in the last 24 hours "
                f"(from {format_date(YESTERDAY)} to {format_date(TODAY)}).\n"
                f"If nothing in 24h, Just return an empty result.\n\n"
                f"Return ONLY a raw JSON array (no markdown, no code fences, no explanation):\n"
                f'[{{"title":"short title describing the post","summary":"what he posted about and key insights in 1-2 sentences",'
                f'"url":"direct link to the post, article, or video",'
                f'"source":"Medium / YouTube","importance":"high"}}]\n\n'
                f"Rules:\n"
                f"- Maximum 3 items\n"
                f"- Do NOT search for other people named Hubert Dudek\n"
                f"- Do NOT guess or fabricate post content\n"
                f"- Return [] if his pages show no recent activity"
            ),
        },

        # ---------------------------------------------------------------
        # DATA ENGINEERING — pin official project/platform sources
        # ---------------------------------------------------------------
        {
            "id": "dataeng",
            "label": "Data Engineering",
            "prompt": (
                f"You are a data engineering news extractor. "
                f"Check ONLY these official sources — do NOT search the broader web:\n{dataeng_urls}\n\n"
                f"Find releases, announcements, or blog posts published in the last 24 hours "
                f"(from {format_date(YESTERDAY)} to {format_date(TODAY)}).\n"
                f"If nothing in 24h, Just return an empty result.\n\n"
                f"Return ONLY a raw JSON array (no markdown, no code fences, no explanation):\n"
                f'[{{"title":"...","summary":"1-2 sentence summary of what changed and why data engineers should care",'
                f'"url":"exact URL from the source","source":"e.g. dbt Blog / Apache Iceberg GitHub",'
                f'"importance":"high"}}]\n\n'
                f"Rules:\n"
                f"- Maximum 4 items, prioritise breaking changes and major releases\n"
                f"- Only include items actually found at those URLs\n"
                f"- Never fabricate URLs\n"
                f"- Return [] only if pages are unreachable or truly have no recent content"
            ),
        },

        # ---------------------------------------------------------------
        # AI & LLMs — pin official lab blogs and release pages
        # ---------------------------------------------------------------
        {
            "id": "ai",
            "label": "AI & LLMs",
            "prompt": (
                f"You are an AI news extractor. "
                f"Check ONLY these official sources — do NOT search the broader web:\n{ai_urls}\n\n"
                f"Find model releases, research announcements, or major product launches published in the last 24 hours "
                f"(from {format_date(YESTERDAY)} to {format_date(TODAY)}).\n"
                f"If nothing in 24h,  Just return an empty result.\n\n"
                f"Return ONLY a raw JSON array (no markdown, no code fences, no explanation):\n"
                f'[{{"title":"...","summary":"1-2 sentence summary explaining the development and its significance",'
                f'"url":"exact URL from the source","source":"e.g. OpenAI Blog / Anthropic News",'
                f'"importance":"high"}}]\n\n'
                f"Rules:\n"
                f"- Maximum 5 items\n"
                f"- Only include items actually found at those URLs\n"
                f"- Never fabricate URLs\n"
                f"- Return [] only if truly no recent content found"
            ),
        },

        # ---------------------------------------------------------------
        # VAIBHAV SISINITY - exact YouTube and Instagram pages
        # ---------------------------------------------------------------
        {
            "id": "vaibhav",
            "label": "Vaibhav Sisinity",
            "prompt": (
                f"You are a content tracker for a specific creator. "
                f"Check ONLY these exact pages for Vaibhav Sisinty's latest content:\n{vaibhav_urls}\n\n"
                f"Find videos, posts, or content published in the last 24 hours "
                f"(from {format_date(YESTERDAY)} to {format_date(TODAY)}).\n"
                f"If nothing in 24h, Just return an empty result.\n\n"
                f"Return ONLY a raw JSON array (no markdown, no code fences, no explanation):\n"
                f'[{{"title":"...","summary":"what the video/post is about and key takeaways",'
                f'"url":"direct link to the YouTube video or Instagram post",'
                f'"source":"YouTube / Instagram","importance":"high"}}]\n\n'
                f"Rules:\n"
                f"- Maximum 3 items\n"
                f"- Do NOT search for other people; only Vaibhav Sisinty\n"
                f"- Prefer YouTube links over others if available\n"
                f"- Return [] if truly no content found at those pages"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# All functions below are unchanged from original
# ---------------------------------------------------------------------------

def get_gemini_api_keys() -> List[str]:
    api_keys = [
        key.strip()
        for key in [
            os.getenv("GEMINI_API_KEY"),
            os.getenv("GEMINI_API_KEY_2"),
        ]
        if key and key.strip()
    ]
    if not api_keys:
        raise EnvironmentError("Please set the GEMINI_API_KEY environment variable.")
    return api_keys


def is_gemini_quota_error(exc: Exception) -> bool:
    error_text = str(exc).lower()
    return "429" in error_text or "resource_exhausted" in error_text or "quota" in error_text


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Please set the {name} environment variable.")
    return value


def save_debug_response(category_id: str, raw_text: str) -> None:
    os.makedirs(DEBUG_RESPONSE_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DEBUG_RESPONSE_DIR, f"{timestamp}_{category_id}.txt")
    with open(path, "w", encoding="utf-8") as file:
        file.write(raw_text)
    print(f"  saved raw Gemini response for debugging: {path}")


def find_latest_cached_response_path(category_id: str) -> str | None:
    if not os.path.isdir(DEBUG_RESPONSE_DIR):
        return None

    today_prefix = TODAY.strftime("%Y%m%d")
    filename_suffix = f"_{category_id}.txt"
    candidates = [
        os.path.join(DEBUG_RESPONSE_DIR, filename)
        for filename in os.listdir(DEBUG_RESPONSE_DIR)
        if filename.startswith(today_prefix) and filename.endswith(filename_suffix)
    ]

    if not candidates:
        return None

    return max(candidates, key=os.path.getmtime)


def load_cached_category_news(category: Dict[str, Any]) -> List[Dict[str, Any]] | None:
    cached_path = find_latest_cached_response_path(category["id"])
    if not cached_path:
        return None

    print(f"Using cached raw Gemini response for {category['label']}: {cached_path}")
    with open(cached_path, "r", encoding="utf-8") as file:
        raw = file.read()

    items = parse_model_response(raw, category["id"])
    print(f"  -> {len(items)} cached items")
    return items


def parse_model_response(raw_text: str, category_id: str = "unknown") -> List[Dict[str, Any]]:
    raw_text = raw_text.strip()
    raw_text = re.sub(r"```json|```", "", raw_text, flags=re.IGNORECASE).strip()
    match = re.search(r"\[[\s\S]*\]", raw_text)
    if not match:
        if raw_text:
            save_debug_response(category_id, raw_text)
        return []

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        save_debug_response(category_id, raw_text)
        return []

    if not isinstance(parsed, list):
        return []

    return [item for item in parsed if isinstance(item, dict)]


def fetch_category_news(category: Dict[str, Any]) -> List[Dict[str, Any]]:
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        max_output_tokens=1000,
        temperature=0.0,
        tools=[grounding_tool],
    )

    last_quota_error: Exception | None = None
    for key_index, api_key in enumerate(get_gemini_api_keys(), start=1):
        try:
            if key_index > 1:
                print(f"  primary Gemini key hit quota; retrying with Gemini API key {key_index}...")
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=category["prompt"],
                config=config,
            )
            break
        except Exception as exc:
            if is_gemini_quota_error(exc):
                last_quota_error = exc
                continue
            raise
    else:
        raise RuntimeError("All configured Gemini API keys hit quota/resource limits.") from last_quota_error

    # Always save raw response for debugging (not just on failure)
    raw = response.text or ""
    save_debug_response(category["id"], raw)

    return parse_model_response(raw, category["id"])


def category_labels() -> Dict[str, str]:
    return {
        "databricks": "🔶 DATABRICKS & SPARK",
        "hubert": "👤 HUBERT DUDEK",
        "dataeng": "⚙️ DATA ENGINEERING",
        "ai": "🤖 AI & LLMs",
        "vaibhav": "🎬 VAIBHAV SISINITY",
    }


def format_whatsapp_header() -> str:
    return "\n".join(
        [
            "🗞️ *DAILY TECH DIGEST*",
            f"📅 _{format_date(TODAY)}_",
            f"⏱️ _Last 24h: {format_date(YESTERDAY)} → {format_date(TODAY)}_",
        ]
    )


def format_whatsapp_overview(feeds: Dict[str, List[Dict[str, Any]]]) -> str:
    labels = category_labels()
    total_items = sum(len(items) for items in feeds.values())
    lines = [
        format_whatsapp_header(),
        "",
        f"📊 *{total_items} stories today*",
        "─────────────────────",
    ]

    for category in build_categories():
        count = len(feeds.get(category["id"], []))
        dot = "🟢" if count > 0 else "⚪"
        lines.append(f"{dot} {labels[category['id']]}: *{count} items*")

    lines.append("─────────────────────")
    return "\n".join(lines)


def format_news_item(label: str, index: int, item: Dict[str, Any]) -> str:
    title = item.get("title", "Untitled")
    summary = item.get("summary", "")
    url = item.get("url", "")
    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"*{label}* · #{index}",
        f"📌 *{title}*",
        f"_{summary}_" if summary else "",
    ]
    if url:
        lines.append(f"🔗 {url}")
    return "\n".join(line for line in lines if line)


def format_no_news_item(label: str) -> str:
    return f"━━━━━━━━━━━━━━━━━━━━━\n*{label}*\n😴 _No updates in the last 24h_"


def build_whatsapp_item_blocks(feeds: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    labels = category_labels()
    blocks: List[str] = []
    for category in build_categories():
        items = feeds.get(category["id"], [])
        if not items:
            blocks.append(format_no_news_item(labels[category["id"]]))
        else:
            for index, item in enumerate(items, start=1):
                blocks.append(format_news_item(labels[category["id"]], index, item))
    return blocks


def split_oversized_block(block: str, max_length: int) -> List[str]:
    lines = block.splitlines()
    chunks: List[str] = []
    current = ""

    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= max_length:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(line) > max_length:
            chunks.append(line[:max_length])
            line = line[max_length:]
        current = line

    if current:
        chunks.append(current)
    return chunks


def format_whatsapp_messages(feeds: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    overview = format_whatsapp_overview(feeds)
    blocks = build_whatsapp_item_blocks(feeds)

    if not blocks:
        return [f"{overview}\n\n😴 _No news found across all sources today._"]

    messages: List[str] = [overview]
    current = ""

    for block in blocks:
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= TWILIO_MAX_BODY_LENGTH:
            current = candidate
            continue

        if current:
            messages.append(current)

        if len(block) <= TWILIO_MAX_BODY_LENGTH:
            current = block
            continue

        oversized_chunks = split_oversized_block(block, TWILIO_MAX_BODY_LENGTH)
        for chunk in oversized_chunks[:-1]:
            messages.append(chunk)
        current = oversized_chunks[-1]

    if current:
        messages.append(current)

    return messages


def format_whatsapp_address(number: str) -> str:
    number = number.strip()
    if number.lower().startswith("whatsapp:"):
        return number
    return f"whatsapp:{number}"


def send_whatsapp_message(message: str) -> str:
    account_sid = get_required_env("TWILIO_ACCOUNT_SID")
    auth_token = get_required_env("TWILIO_AUTH_TOKEN")
    from_number = get_required_env("TWILIO_WHATSAPP_FROM")
    to_number = get_required_env("TWILIO_WHATSAPP_TO")
    print(f"Sending WhatsApp message ({len(message)} characters)...")

    response = requests.post(
        TWILIO_MESSAGES_URL.format(account_sid=account_sid),
        data={
            "From": format_whatsapp_address(from_number),
            "To": format_whatsapp_address(to_number),
            "Body": message,
        },
        auth=(account_sid, auth_token),
        timeout=30,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            details = response.json()
        except ValueError:
            details = response.text
        raise RuntimeError(f"Twilio rejected the WhatsApp message: {details}") from exc

    return response.json()["sid"]


def get_whatsapp_message_status(message_sid: str) -> Dict[str, Any]:
    account_sid = get_required_env("TWILIO_ACCOUNT_SID")
    auth_token = get_required_env("TWILIO_AUTH_TOKEN")

    response = requests.get(
        TWILIO_MESSAGE_URL.format(account_sid=account_sid, message_sid=message_sid),
        auth=(account_sid, auth_token),
        timeout=30,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            details = response.json()
        except ValueError:
            details = response.text
        raise RuntimeError(f"Could not check Twilio message status: {details}") from exc

    return response.json()


def wait_for_whatsapp_message_status(message_sid: str) -> Dict[str, Any]:
    status_details: Dict[str, Any] = {}

    for attempt in range(1, TWILIO_STATUS_CHECK_ATTEMPTS + 1):
        status_details = get_whatsapp_message_status(message_sid)
        status = status_details.get("status", "unknown")
        print(f"  Twilio status check {attempt}/{TWILIO_STATUS_CHECK_ATTEMPTS}: {status}")

        if status not in {"accepted", "queued", "sending"}:
            break

        if attempt < TWILIO_STATUS_CHECK_ATTEMPTS:
            time.sleep(TWILIO_STATUS_CHECK_DELAY_SECONDS)

    return status_details


def print_whatsapp_delivery_result(message_sid: str, status_details: Dict[str, Any]) -> None:
    status = status_details.get("status", "unknown")
    error_code = status_details.get("error_code")
    error_message = status_details.get("error_message")

    if status in {"sent", "delivered"}:
        print(f"  WhatsApp message {message_sid} was {status}.")
        return

    if status in {"undelivered", "failed"}:
        print(f"  WhatsApp message {message_sid} was {status}.")
        if error_code or error_message:
            print(f"  Twilio error: {error_code or 'no code'} - {error_message or 'no message'}")
        return

    print(f"  WhatsApp message {message_sid} is still {status}; check Twilio logs for final delivery.")


def fetch_all_categories() -> Dict[str, List[Dict[str, Any]]]:
    results: Dict[str, List[Dict[str, Any]]] = {}
    for category in build_categories():
        results[category["id"]] = []
        cached_items = load_cached_category_news(category)
        if cached_items is not None:
            results[category["id"]] = cached_items
            continue

        for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
            try:
                print(f"Fetching {category['label']} (attempt {attempt}/{MAX_FETCH_ATTEMPTS})...")
                items = fetch_category_news(category)
                results[category["id"]] = items
                print(f"  -> {len(items)} items")
                if items or attempt == MAX_FETCH_ATTEMPTS:
                    break
                print("  empty result; retrying...")
            except Exception as exc:
                print(f"  x Error fetching {category['label']}: {exc}")
                if attempt == MAX_FETCH_ATTEMPTS:
                    break
    return results


def main() -> int:
    feeds = fetch_all_categories()
    messages = format_whatsapp_messages(feeds)
    message_sids = []
    for index, message in enumerate(messages, start=1):
        print(f"Sending batch {index}/{len(messages)}...")
        message_sid = send_whatsapp_message(message)
        message_sids.append(message_sid)
        status_details = wait_for_whatsapp_message_status(message_sid)
        print_whatsapp_delivery_result(message_sid, status_details)
    print(f"WhatsApp messages sent successfully. Message SIDs: {', '.join(message_sids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
