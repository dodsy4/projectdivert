import hashlib
from pathlib import Path


_original_md5 = hashlib.md5


def _compat_md5(*args, **kwargs):
    kwargs.pop("usedforsecurity", None)
    return _original_md5(*args, **kwargs)


hashlib.md5 = _compat_md5

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageTemplate,
    Paragraph,
    Spacer,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT_PATH = OUTPUT_DIR / "project_divert_app_summary.pdf"


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Kicker",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#5B6B79"),
            spaceAfter=2,
            uppercase=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=24,
            textColor=colors.HexColor("#17324D"),
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Deck",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#334155"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            textColor=colors.HexColor("#17324D"),
            spaceBefore=2,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#243241"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="AppBullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=11.5,
            leftIndent=0,
            textColor=colors.HexColor("#243241"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Footer",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#64748B"),
        )
    )
    return styles


def bullet_list(items, style):
    return ListFlowable(
        [
            ListItem(Paragraph(item, style), leftIndent=0)
            for item in items
        ],
        bulletType="bullet",
        start="circle",
        bulletFontName="Helvetica",
        bulletFontSize=7,
        leftIndent=10,
        bulletOffsetY=1,
        spaceBefore=0,
        spaceAfter=4,
    )


def section(title, content, styles):
    return KeepTogether(
        [
            Paragraph(title, styles["Section"]),
            content,
        ]
    )


def build_story(styles):
    what_it_is = (
        "Project Divert is a Flask-based waste and materials platform with an Expo mobile app. "
        "Repo evidence shows server-rendered workflows, JSON APIs, dispatch, compliance, billing, "
        "and realtime request tracking for waste-removal operations."
    )
    who_its_for = (
        "Primary users appear to be customers booking waste-removal jobs, drivers/carriers fulfilling "
        "them, and admin/ops teams managing dispatch, compliance, auth security, and billing."
    )

    features = [
        "Lists reusable materials, supports search/filter views, and accepts material requests.",
        "Captures waste-removal bookings with pickup details, scheduling, notes, and match radius.",
        "Matches nearby providers and creates ranked dispatch offers based on distance and quality signals.",
        "Provides auth APIs for login, signup, refresh, email verification, password reset, and logout.",
        "Streams request events and latest vehicle location for live customer and driver updates.",
        "Tracks compliance documents for requests, drivers, and carrier companies, including admin review.",
        "Supports billing workflows, Stripe-backed charges/refunds/payouts, and push subscription APIs.",
    ]

    architecture = [
        "<b>Frontend/UI:</b> Flask templates under <font face='Courier'>templates/</font> for home, materials, maps, auth, admin dispatch, and request forms; React Native/Expo client in <font face='Courier'>mobile-app/</font>.",
        "<b>Backend:</b> Single Flask app in <font face='Courier'>app.py</font> with HTML routes and <font face='Courier'>/api/v1/*</font> endpoints.",
        "<b>Data layer:</b> SQLAlchemy models with Alembic migrations; Postgres configured via <font face='Courier'>SQLALCHEMY_DATABASE_URI</font> / <font face='Courier'>DATABASE_URL</font>.",
        "<b>Reference data:</b> Pandas-backed supplier, site, and carbon-offset data loaded from repo CSV/XLSX files and seedable via <font face='Courier'>flask seed-reference-data</font>.",
        "<b>Services/integrations:</b> Google Maps geocoding/drive-time, SendGrid-compatible email, optional Redis rate limiting, optional S3 compliance storage, Stripe payments, Expo push.",
        "<b>Flow:</b> Customer submits request -> backend stores job + provider matches/offers -> driver/admin accepts and updates status/location -> SSE and push notify mobile clients -> admin reviews compliance/billing.",
    ]

    run_steps = [
        "<b>Backend:</b> <font face='Courier'>pip install -r requirements.txt</font>",
        "<b>Config:</b> set env from <font face='Courier'>.env.example</font>; minimum repo-documented values are <font face='Courier'>SECRET_KEY</font>, <font face='Courier'>DATABASE_URL</font>, and <font face='Courier'>GOOGLE_MAPS_API_KEY</font>.",
        "<b>Database:</b> <font face='Courier'>flask db upgrade</font> then <font face='Courier'>flask seed-reference-data</font>",
        "<b>Run web/API:</b> <font face='Courier'>python app.py</font> locally, or <font face='Courier'>gunicorn app:app</font> for deploys",
        "<b>Mobile (optional):</b> in <font face='Courier'>mobile-app/</font>, copy <font face='Courier'>.env.example</font>, set <font face='Courier'>EXPO_PUBLIC_API_BASE_URL</font>, then run <font face='Courier'>npm install</font> and <font face='Courier'>npm run start</font>.",
    ]

    story = [
        Paragraph("Repo Summary", styles["Kicker"]),
        Paragraph("Project Divert", styles["SummaryTitle"]),
        Paragraph(
        "One-page app summary generated from repository evidence only.",
            styles["Deck"],
        ),
        section("What It Is", Paragraph(what_it_is, styles["Body"]), styles),
        section("Who It's For", Paragraph(who_its_for, styles["Body"]), styles),
        section("What It Does", bullet_list(features, styles["AppBullet"]), styles),
        FrameBreak(),
        section("How It Works", bullet_list(architecture, styles["AppBullet"]), styles),
        Spacer(1, 4),
        section("How To Run", bullet_list(run_steps, styles["AppBullet"]), styles),
        Spacer(1, 8),
        Paragraph(
            "Evidence sources inspected: app.py, config.py, forms.py, tests/test_app_smoke.py, "
            "mobile-app/README.md, mobile-app/App.tsx, render.yaml, DEPLOY.md, and repo file structure.",
            styles["Footer"],
        ),
    ]
    return story


def draw_background(canvas, doc):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#F8FAFC"))
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#DCE9F5"))
    canvas.rect(0, height - 34 * mm, width, 34 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#17324D"))
    canvas.rect(0, height - 15 * mm, width, 4 * mm, fill=1, stroke=0)
    canvas.restoreState()


def build_pdf():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    styles = build_styles()
    doc = BaseDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=16 * mm,
        bottomMargin=12 * mm,
    )

    gap = 7 * mm
    frame_width = (doc.width - gap) / 2
    frame_height = doc.height
    frames = [
        Frame(doc.leftMargin, doc.bottomMargin, frame_width, frame_height, id="left"),
        Frame(
            doc.leftMargin + frame_width + gap,
            doc.bottomMargin,
            frame_width,
            frame_height,
            id="right",
        ),
    ]
    doc.addPageTemplates([PageTemplate(id="summary", frames=frames, onPage=draw_background)])
    doc.build(build_story(styles))


if __name__ == "__main__":
    build_pdf()
    print(OUTPUT_PATH)
