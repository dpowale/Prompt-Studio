THEME_PRESETS = {
  "Dark": {
    "page_bg": "#0a0f19",
    "panel_bg": "#101726",
    "panel_bg_2": "#131c2e",
    "text": "#ffffff",
    "muted": "#8a94ab",
    "border": "#243049",
    "accent": "#6d7cff",
    "accent_2": "#a855f7",
    "accent_soft": "rgba(109,124,255,0.14)",
    "success": "#4ade80",
    "warning": "#d39b3b",
    "shadow": "0 12px 30px rgba(0, 0, 0, 0.18)",
  },
  "Light": {
    "page_bg": "#f5f7fb",
    "panel_bg": "#ffffff",
    "panel_bg_2": "#eef3fb",
    "text": "#132238",
    "muted": "#5f6f86",
    "border": "#d9e3f0",
    "accent": "#3c63ff",
    "accent_2": "#6b3df0",
    "accent_soft": "rgba(60,99,255,0.12)",
    "success": "#1e8f5a",
    "warning": "#b57a14",
    "shadow": "0 12px 30px rgba(15, 23, 42, 0.08)",
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
      }}
      
      /* Essential Streamlit Overrides to fix 'white on white' bugs */
      .stApp, .stApp > header {{
        background-color: var(--page-bg) !important;
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
        background-color: var(--panel-bg) !important;
        border-right: 1px solid var(--border-color) !important;
      }}

      /* Widget Labels */
      small, .stCaption, [data-testid="stWidgetLabel"] p {{
        color: var(--text-color) !important;
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
        color-scheme: dark;
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
      }}

      /* Primary Button */
      [data-testid="baseButton-primary"],
      [data-testid="baseButton-primary"] *,
      button[kind="primary"],
      button[kind="primary"] * {{
        background-color: var(--accent-color) !important;
        color: #ffffff !important;
        border: none !important;
      }}
      
      /* UI Elements */
      div[data-testid="stMetric"], .stExpander > details {{
        background-color: var(--panel-bg) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
      }}
      
      /* Checkbox & radio text */
      [data-testid="stRadio"] label span, [data-testid="stCheckbox"] label span {{
        color: var(--text-color) !important;
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
        background: linear-gradient(135deg, var(--panel-bg) 0%, var(--panel-bg-2) 100%);
        border: 1px solid var(--border-color);
        border-radius: 20px;
        box-shadow: var(--shadow-color);
        padding: 1.4rem 1.5rem;
        margin: 0.4rem 0 1rem;
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
        font-size: 2.1rem;
        font-weight: 700;
        margin: 0 0 0.3rem;
      }}

      .hero-subtitle {{
        color: var(--muted-color);
        font-size: 1rem;
        line-height: 1.6;
        margin: 0 0 1rem;
      }}

      .chip-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
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
        border-radius: 16px;
        padding: 1rem 1.1rem;
        box-shadow: var(--shadow-color);
        margin-bottom: 0.9rem;
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
        border-radius: 16px;
        border: 1px solid var(--border-color);
        background: var(--panel-bg);
        padding: 0.95rem 1rem;
      }}

      .step-card.active {{
        background: linear-gradient(135deg, var(--accent-soft) 0%, var(--panel-bg) 100%);
        border-color: var(--accent-color);
      }}

      .step-card.done {{
        border-color: rgba(34, 197, 94, 0.35);
      }}

      .step-label {{
        color: var(--muted-color);
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.28rem;
      }}

      .step-name {{
        color: var(--text-color);
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: 0.15rem;
      }}

      .step-note {{
        color: var(--muted-color);
        font-size: 0.88rem;
        line-height: 1.45;
      }}

      .step-status {{
        color: var(--accent-color);
        font-weight: 700;
      }}

      .helper-card {{
        background: linear-gradient(180deg, var(--panel-bg) 0%, var(--panel-bg-2) 100%);
        border: 1px dashed var(--border-color);
        border-radius: 14px;
        padding: 0.95rem 1rem;
        margin: 0.35rem 0 0.8rem;
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
        border-radius: 14px;
        padding: 0.9rem 1rem;
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
        background: linear-gradient(135deg, var(--panel-bg) 0%, var(--panel-bg-2) 100%);
        border: 1px solid var(--border-color);
        border-radius: 20px;
        padding: 1.15rem 1.25rem;
        margin: 0.4rem 0 1rem;
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
        border-radius: 14px;
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
        border-radius: 10px 10px 0 0 !important;
        padding: 0.55rem 0.9rem !important;
      }}

      [data-testid="stTabs"] [aria-selected="true"] {{
        background: var(--accent-soft) !important;
        border-color: var(--accent-color) !important;
      }}

    </style>
    """
