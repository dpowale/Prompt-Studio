THEME_PRESETS = {
  "Dark": {
    "page_bg": "#0f1720",
    "panel_bg": "#131d28",
    "panel_bg_2": "#182433",
    "text": "#edf2f7",
    "muted": "#9aa7b7",
    "border": "#2a384a",
    "accent": "#2563eb",
    "accent_2": "#1d4ed8",
    "accent_soft": "rgba(37,99,235,0.14)",
    "success": "#34d399",
    "warning": "#f59e0b",
    "shadow": "0 14px 36px rgba(0, 0, 0, 0.24)",
  },
  "Light": {
    "page_bg": "#f4f7fb",
    "panel_bg": "#ffffff",
    "panel_bg_2": "#eef3f9",
    "text": "#17212b",
    "muted": "#617284",
    "border": "#d6deea",
    "accent": "#2563eb",
    "accent_2": "#1d4ed8",
    "accent_soft": "rgba(37,99,235,0.10)",
    "success": "#15803d",
    "warning": "#b45309",
    "shadow": "0 12px 30px rgba(15, 23, 42, 0.10)",
  },
}

def theme_css(mode: str) -> str:
    t = THEME_PRESETS.get(mode, THEME_PRESETS["Light"])
    return f"""
    <style>
      :root {{
        --page-bg: {t['page_bg']};
        --panel-bg: {t['panel_bg']};
        --panel-bg-2: {t['panel_bg_2']};
        --text-color: {t['text']};
        --muted-color: {t['muted']};
        --border-color: {t['border']};
        --accent-color: {t['accent']};
        --accent-2: {t['accent_2']};
        --accent-soft: {t['accent_soft']};
        --success-color: {t['success']};
        --warning-color: {t['warning']};
        --shadow-color: {t['shadow']};
        --body-font: "Segoe UI", "Aptos", "Helvetica Neue", sans-serif;
        --display-font: "Segoe UI", "Aptos", "Helvetica Neue", sans-serif;
        --radius-lg: 22px;
        --radius-md: 16px;
      }}

      html, body, [class*="css"]  {{
        font-family: var(--body-font);
      }}
      
      /* Essential Streamlit Overrides to fix 'white on white' bugs */
      .stApp, .stApp > header {{
        background:
          radial-gradient(circle at top left, rgba(37,99,235,0.06), transparent 26%),
          radial-gradient(circle at top right, rgba(15,23,42,0.05), transparent 20%),
          linear-gradient(180deg, var(--page-bg) 0%, var(--page-bg) 100%) !important;
      }}

      .block-container {{
        max-width: 1180px;
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
      }}

      h1, h2, h3, .hero-title, .section-title, .score-title {{
        font-family: var(--display-font);
        letter-spacing: -0.02em;
      }}
      
      [data-testid="stMarkdownContainer"] p,
      [data-testid="stMarkdownContainer"] span,
      [data-testid="stMarkdownContainer"] h1,
      [data-testid="stMarkdownContainer"] h2,
      [data-testid="stMarkdownContainer"] h3,
      [data-testid="stMarkdownContainer"] h4,
      [data-testid="stMarkdownContainer"] li,
      [data-testid="stText"], p {{
        color: var(--text-color) !important;
      }}
      
      [data-testid="stSidebar"], [data-testid="stSidebarContent"] {{
        background:
          linear-gradient(180deg, var(--panel-bg) 0%, var(--panel-bg-2) 100%) !important;
        border-right: 1px solid var(--border-color) !important;
      }}

      [data-testid="stSidebar"] .block-container {{
        padding-top: 1.15rem;
      }}

      /* Widget Labels */
      small, .stCaption, [data-testid="stWidgetLabel"] p {{
        color: var(--text-color) !important;
      }}

      [data-testid="stWidgetLabel"] p {{
        font-size: 1rem !important;
        line-height: 1.5 !important;
        font-weight: 600 !important;
      }}
      
      /* Input elements */
      .stTextInput > div > div > input, 
      .stTextInput input,
      .stTextArea > div > div > textarea,
      .stTextArea textarea,
      [data-baseweb="select"] > div,
      [data-baseweb="select"] span,
      [data-baseweb="select"] div,
      [data-testid="stSelectbox"] div,
      [data-testid="stSelectbox"] span,
      [data-baseweb="base-input"],
      [data-baseweb="base-input"] input {{
        background-color: var(--panel-bg-2) !important;
        color: var(--text-color) !important;
        border-color: var(--border-color) !important;
        border-radius: 14px !important;
      }}

      [data-testid="stSelectbox"] label,
      [data-testid="stSelectbox"] [data-baseweb="select"] span,
      [data-testid="stSelectbox"] [data-baseweb="select"] div {{
        font-size: 1.02rem !important;
        line-height: 1.45 !important;
      }}

      .stTextInput input,
      .stTextArea textarea {{
        min-height: 3rem;
      }}

      .stTextArea textarea {{
        font-size: 1rem !important;
        line-height: 1.55;
      }}
      
      /* Dropdowns / Menus */
      div[data-baseweb="popover"],
      div[data-baseweb="popover"] > div,
      [data-baseweb="menu"] > div,
      [data-baseweb="menu"] ul,
      ul[role="listbox"] li,
      div[role="listbox"] div,
      div[role="listbox"] span {{
        background-color: var(--panel-bg-2) !important;
        color: var(--text-color) !important;
      }}
      
      /* Placeholder text fallback */
      .stTextInput > div > div > input::placeholder, 
      .stTextArea > div > div > textarea::placeholder {{
        color: var(--muted-color) !important;
        opacity: 0.8 !important;
      }}
      
      /* Buttons */
      .stButton button,
      .stButton button *,
      .stDownloadButton button,
      .stDownloadButton button * {{
        background-color: var(--panel-bg-2) !important;
        color: var(--text-color) !important;
        border-color: var(--border-color) !important;
        border-radius: 999px !important;
        font-weight: 600 !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease !important;
      }}

      .stButton button:hover,
      .stDownloadButton button:hover {{
        transform: translateY(-1px);
        box-shadow: var(--shadow-color);
      }}

      /* Primary Button */
      [data-testid="baseButton-primary"],
      [data-testid="baseButton-primary"] *,
      button[kind="primary"],
      button[kind="primary"] * {{
        background: linear-gradient(135deg, var(--accent-color) 0%, var(--accent-2) 100%) !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0 12px 22px rgba(15, 118, 110, 0.24) !important;
      }}
      
      /* UI Elements */
      div[data-testid="stMetric"], .stExpander > details {{
        background-color: var(--panel-bg) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius-md) !important;
        box-shadow: var(--shadow-color);
      }}

      .stExpander > details:hover,
      div[data-testid="stMetric"]:hover {{
        border-color: var(--accent-color) !important;
      }}
      
      /* Checkbox & radio text */
      [data-testid="stRadio"] label span, [data-testid="stCheckbox"] label span {{
        color: var(--text-color) !important;
      }}

      /* Toggle (e.g. DSPy): show green when ON instead of Streamlit's default red */
      [data-testid="stCheckbox"] label:has(input[aria-checked="true"]) > div:first-of-type,
      [data-testid="stCheckbox"] [role="switch"][aria-checked="true"],
      [data-testid="stCheckbox"] [aria-checked="true"] {{
        background-color: var(--success-color) !important;
        border-color: var(--success-color) !important;
      }}
      
      /* Alert Text */
      [data-testid="stAlert"] {{
        color: var(--text-color) !important;
        background-color: var(--panel-bg-2) !important; 
        border: 1px solid var(--border-color) !important;
      }}
      [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {{
        color: var(--text-color) !important;
      }}

      .hero-shell {{
        position: relative;
        overflow: hidden;
        background:
          radial-gradient(circle at top right, rgba(37,99,235,0.10), transparent 28%),
          linear-gradient(135deg, var(--panel-bg) 0%, var(--panel-bg-2) 100%);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow-color);
        padding: 1.7rem 1.7rem 1.5rem;
        margin: 0.4rem 0 1.15rem;
      }}

      .hero-shell::after {{
        content: "";
        position: absolute;
        inset: auto -10% -35% auto;
        width: 280px;
        height: 280px;
        background: radial-gradient(circle, rgba(37,99,235,0.12), transparent 62%);
        pointer-events: none;
      }}

      .hero-eyebrow {{
        color: var(--accent-color);
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
      }}

      .hero-title {{
        color: var(--text-color);
        font-size: 2.35rem;
        font-weight: 700;
        line-height: 1.08;
        max-width: 14ch;
        margin: 0 0 0.45rem;
      }}

      .hero-subtitle {{
        color: var(--muted-color);
        font-size: 1.02rem;
        line-height: 1.65;
        margin: 0;
        max-width: none;
        white-space: nowrap;
      }}

      .chip-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
      }}

      .hero-metrics {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.8rem;
        margin-top: 1.15rem;
      }}

      .hero-metric {{
        background: rgba(255,255,255,0.04);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-md);
        padding: 0.95rem 1rem;
        backdrop-filter: blur(6px);
      }}

      .hero-metric-value {{
        color: var(--text-color);
        font-size: 1.2rem;
        font-weight: 800;
        margin-bottom: 0.18rem;
      }}

      .hero-metric-label {{
        color: var(--muted-color);
        font-size: 0.84rem;
        line-height: 1.45;
      }}

      .chip {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        background: var(--accent-soft);
        border: 1px solid var(--border-color);
        color: var(--text-color);
        font-size: 0.86rem;
        font-weight: 600;
      }}

      .section-card {{
        background: var(--panel-bg);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-md);
        padding: 1.05rem 1.15rem;
        box-shadow: var(--shadow-color);
        margin-bottom: 1rem;
      }}

      .section-kicker {{
        color: var(--accent-color);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
      }}

      .section-title {{
        color: var(--text-color);
        font-size: 1.2rem;
        font-weight: 700;
        margin: 0 0 0.2rem;
      }}

      .section-body {{
        color: var(--muted-color);
        font-size: 0.96rem;
        line-height: 1.55;
        margin: 0;
      }}

      .stepper-grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.8rem;
        margin: 0.4rem 0 0.75rem;
      }}

      .step-card {{
        border-radius: var(--radius-md);
        border: 1px solid var(--border-color);
        background: var(--panel-bg);
        padding: 0.95rem 1rem;
        min-height: 120px;
        box-shadow: var(--shadow-color);
      }}

      .step-card.active {{
        background: linear-gradient(135deg, var(--accent-soft) 0%, var(--panel-bg) 100%);
        border-color: var(--accent-color);
        box-shadow: 0 10px 24px rgba(37, 99, 235, 0.10);
      }}

      .step-card.done {{
        border-color: rgba(34, 197, 94, 0.35);
      }}

      .step-label {{
        color: var(--muted-color);
        font-size: 0.92rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.4rem;
        line-height: 1.45;
      }}

      .step-name {{
        color: var(--text-color);
        font-size: 1.16rem;
        font-weight: 700;
        margin-bottom: 0.28rem;
        line-height: 1.35;
      }}

      .step-note {{
        color: var(--muted-color);
        font-size: 1rem;
        line-height: 1.6;
      }}

      .step-status {{
        color: var(--accent-color);
        font-weight: 700;
      }}

      .helper-card {{
        background: var(--panel-bg);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-md);
        padding: 0.95rem 1rem;
        margin: 0.35rem 0 0.8rem;
        box-shadow: var(--shadow-color);
      }}

      .helper-title {{
        color: var(--text-color);
        font-size: 0.98rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
      }}

      .helper-body {{
        color: var(--muted-color);
        font-size: 0.9rem;
        line-height: 1.5;
      }}

      .mini-grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.8rem;
        margin: 0.5rem 0 1rem;
      }}

      .mini-card {{
        background: var(--panel-bg);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-md);
        padding: 0.9rem 1rem;
        box-shadow: var(--shadow-color);
      }}

      .mini-label {{
        color: var(--muted-color);
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.25rem;
      }}

      .mini-value {{
        color: var(--text-color);
        font-size: 1.05rem;
        font-weight: 700;
        line-height: 1.35;
      }}

      .score-shell {{
        background: var(--panel-bg);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-lg);
        padding: 1.15rem 1.25rem;
        margin: 0.4rem 0 1rem;
        box-shadow: var(--shadow-color);
      }}

      .score-topline {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        margin-bottom: 0.8rem;
      }}

      .score-title {{
        color: var(--text-color);
        font-size: 1.15rem;
        font-weight: 700;
        margin: 0;
      }}

      .score-caption {{
        color: var(--muted-color);
        font-size: 0.92rem;
        margin-top: 0.18rem;
      }}

      .score-pill {{
        min-width: 88px;
        text-align: center;
        padding: 0.5rem 0.8rem;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--text-color);
        font-weight: 800;
        font-size: 1rem;
      }}

      .score-bar {{
        width: 100%;
        height: 10px;
        border-radius: 999px;
        background: rgba(148, 163, 184, 0.18);
        overflow: hidden;
        margin-bottom: 0.8rem;
      }}

      .score-bar-fill {{
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--accent-color) 0%, var(--accent-2) 100%);
      }}

      .history-card {{
        background: var(--panel-bg);
        border: 1px solid var(--border-color);
        border-radius: var(--radius-md);
        padding: 0.9rem 1rem;
        margin-bottom: 0.8rem;
      }}

      .history-title {{
        color: var(--text-color);
        font-weight: 700;
        margin-bottom: 0.2rem;
      }}

      .history-subtitle {{
        color: var(--muted-color);
        font-size: 0.9rem;
      }}

      [data-testid="stTabs"] [role="tablist"] {{
        gap: 0.4rem;
      }}

      [data-testid="stTabs"] [role="tab"] {{
        background: var(--panel-bg) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 14px 14px 0 0 !important;
        padding: 0.55rem 0.9rem !important;
      }}

      [data-testid="stTabs"] [aria-selected="true"] {{
        background: var(--accent-soft) !important;
        border-color: var(--accent-color) !important;
      }}

      @media (max-width: 900px) {{
        .hero-title {{
          font-size: 2rem;
          max-width: none;
        }}

        .hero-subtitle {{
          white-space: normal;
        }}

        .hero-metrics,
        .mini-grid {{
          grid-template-columns: 1fr;
        }}
      }}

    </style>
    """
