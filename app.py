import time
import re
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

# --- CONFIG ---
st.set_page_config(page_title="UX Beauty Benchmark Agent", page_icon="✨", layout="wide")

st.title("✨ UX Beauty Benchmark — Agentic AI UX Designer")
st.caption(
    "Paste a website URL. The Agentic AI UX Designer will think step-by-step and benchmark it "
    "against Apple iOS, Airbnb, Notion, Tesla UI, and Figma."
)

# --- FIXED BENCHMARKS ---
REFERENCE_BENCHMARKS = [
    {"Product / UX Factor": "Apple iOS", "Simplicity": 9, "Navigation Ease": 9, "Personality": 9,
     "Delight/Micro-Interactions": 8, "Accessibility": 8, "Speed & Responsiveness": 9,
     "Emotional Resonance": 9},
    {"Product / UX Factor": "Airbnb", "Simplicity": 9, "Navigation Ease": 9, "Personality": 8,
     "Delight/Micro-Interactions": 8, "Accessibility": 9, "Speed & Responsiveness": 9,
     "Emotional Resonance": 8},
    {"Product / UX Factor": "Notion", "Simplicity": 8, "Navigation Ease": 8, "Personality": 9,
     "Delight/Micro-Interactions": 8, "Accessibility": 8, "Speed & Responsiveness": 8,
     "Emotional Resonance": 9},
    {"Product / UX Factor": "Tesla UI", "Simplicity": 8, "Navigation Ease": 9, "Personality": 9,
     "Delight/Micro-Interactions": 9, "Accessibility": 7, "Speed & Responsiveness": 9,
     "Emotional Resonance": 9},
    {"Product / UX Factor": "Figma", "Simplicity": 8, "Navigation Ease": 9, "Personality": 8,
     "Delight/Micro-Interactions": 9, "Accessibility": 8, "Speed & Responsiveness": 10,
     "Emotional Resonance": 8},
]
UX_FACTORS = [
    "Simplicity",
    "Navigation Ease",
    "Personality",
    "Delight/Micro-Interactions",
    "Accessibility",
    "Speed & Responsiveness",
    "Emotional Resonance",
]

# --- HELPERS ---
def clamp_score(x, lo=1, hi=10):
    return max(lo, min(hi, round(x)))

@st.cache_data(show_spinner=False)
def fetch_html(url: str, timeout=6):
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
    headers = {"User-Agent": "Mozilla/5.0 (compatible; UXBenchmark/1.0)"}
    t0 = time.time()
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        elapsed = time.time() - t0
        content_size = len(r.content or b"")
        r.raise_for_status()
        return {
            "final_url": r.url,
            "status": r.status_code,
            "elapsed": elapsed,
            "size": content_size,
            "text": r.text,
        }
    except Exception as e:
        return {"error": str(e)}

@st.cache_data(show_spinner=False)
def fetch_css_assets(html, base_url, limit=3, timeout=4):
    try:
        soup = BeautifulSoup(html, "html.parser")
        hrefs = []
        for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
            href = link.get("href")
            if href:
                hrefs.append(urljoin(base_url, href))
        hrefs = hrefs[:limit]
        css_texts = []
        headers = {"User-Agent": "Mozilla/5.0 (compatible; UXBenchmark/1.0)"}
        for h in hrefs:
            try:
                r = requests.get(h, headers=headers, timeout=timeout)
                if r.ok and r.text:
                    css_texts.append(r.text[:50000])  # smaller limit for free tier
            except:
                pass
        return "\n".join(css_texts)
    except Exception:
        return ""

def count_colors(css_text: str):
    hex_colors = re.findall(r"#[0-9a-fA-F]{3,8}", css_text or "")
    rgb_colors = re.findall(r"rgb\(\s*\d+,\s*\d+,\s*\d+\s*\)", css_text or "")
    return len(set(hex_colors + rgb_colors))

def cohesion_from_colors(color_count: int):
    if color_count <= 6: return 10
    elif color_count <= 12: return 8
    elif color_count <= 24: return 6
    elif color_count <= 48: return 4
    else: return 2

def analyze_site(url: str):
    res = fetch_html(url)
    if "error" in res:
        return None, res["error"]

    html = res["text"]
    base_url = res["final_url"]
    soup = BeautifulSoup(html, "html.parser")
    css_text = fetch_css_assets(html, base_url)
    palette_count = count_colors(css_text)
    cohesion = cohesion_from_colors(palette_count)

    # Very simplified scoring (light for free tier)
    scores = {
        "Simplicity": clamp_score((cohesion + 8) / 2),
        "Navigation Ease": clamp_score(5 + (1 if soup.find("nav") else 0)),
        "Personality": clamp_score((cohesion + (1 if soup.find("link", rel="icon") else 0) + 6) / 2),
        "Delight/Micro-Interactions": clamp_score(5 + (1 if ":hover" in css_text else 0)),
        "Accessibility": clamp_score(6 + (1 if soup.find(attrs={"aria-label": True}) else 0)),
        "Speed & Responsiveness": clamp_score(10 if res["elapsed"] < 1 else 7),
        "Emotional Resonance": clamp_score((cohesion + 8) / 2),
    }

    debug = {
        "Final URL": base_url,
        "HTTP Status": res.get("status"),
        "Load Time (s)": round(res.get("elapsed", 0), 3),
        "HTML Size (KB)": round((res.get("size", 0) / 1024), 1),
        "CSS Colors Found": palette_count,
        "Palette Cohesion Score": cohesion,
    }
    return scores, debug

def build_table(target_label: str, target_scores: dict):
    rows = []
    for ref in REFERENCE_BENCHMARKS:
        row = {"Product / UX Factor": ref["Product / UX Factor"]}
        for f in UX_FACTORS:
            row[f] = ref[f]
        rows.append(row)
    trow = {"Product / UX Factor": target_label}
    for f in UX_FACTORS:
        trow[f] = target_scores.get(f, None)
    rows.append(trow)

    df = pd.DataFrame(rows)
    df["Total / 70"] = df[UX_FACTORS].sum(axis=1)
    df["Rank"] = df["Total / 70"].rank(method="min", ascending=False).astype(int)
    return df.sort_values(by="Total / 70", ascending=False, ignore_index=True)

# --- UI ---
with st.container():
    col1, col2 = st.columns([2, 1])
    with col1:
        url = st.text_input("Paste a website URL", "https://www.apple.com")
    with col2:
        analyze_btn = st.button("Analyze & Benchmark", use_container_width=True)

if analyze_btn:
    st.subheader("🤖 UX Designer Agent — Thinking Process")
    placeholder = st.empty()

    with st.spinner("Agent is analyzing..."):
        scores, debug = analyze_site(url)

    if scores is None:
        st.error(f"Could not analyze. Error: {debug}")
    else:
        thoughts = [
            f"🧐 Checking structure and colors — found {debug['CSS Colors Found']} colors, cohesion score {debug['Palette Cohesion Score']}.",
            f"🔍 Checking navigation — load time {debug['Load Time (s)']}s, size {debug['HTML Size (KB)']}KB.",
            "🎨 Looking for personality — favicon, custom styles, unique colors.",
            "⚡ Reviewing speed and responsiveness.",
            "♿ Scanning for accessibility signals.",
            "✨ Checking for micro-interactions.",
            "📊 Compiling final benchmark..."
        ]
        for t in thoughts:
            placeholder.markdown(t)
            time.sleep(1.5)

        site_label = urlparse(url).netloc or url
        df = build_table(site_label, scores)

        st.subheader("🏆 Benchmark Table")
        st.dataframe(df, use_container_width=True)

        st.subheader("🎯 Target Site Scores")
        st.json(scores)

        with st.expander("🔧 Diagnostics"):
            st.json(debug)

st.markdown("---")
st.markdown(
"""
### About this Agent
This free, open-source **Agentic AI UX Designer** simulates a human designer's evaluation process.  
It uses lightweight heuristics to assess websites and benchmark them against **Apple iOS, Airbnb, Notion, Tesla UI, and Figma**.
"""
)
