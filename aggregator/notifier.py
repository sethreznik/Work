import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .models import Study

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------

def _insight_bullets(insights: list[str]) -> str:
    if not insights:
        return ""
    items = "".join(
        f'<li style="margin:0 0 8px;font-size:13px;color:#333;line-height:1.5;">{i}</li>'
        for i in insights
    )
    return f"""
        <div style="margin:14px 0 0;">
          <div style="font-size:11px;font-weight:700;color:#1a1a2e;text-transform:uppercase;
                      letter-spacing:.8px;margin-bottom:8px;">Key Insights for Your Team</div>
          <ul style="margin:0;padding-left:18px;">{items}</ul>
        </div>"""


def _study_card(s: Study) -> str:
    pub = s.published.strftime("%Y-%m-%d") if s.published else "Unknown date"

    # Summary block (shown only when analysis succeeded)
    summary_html = ""
    if s.summary:
        summary_html = f"""
        <div style="margin:12px 0 0;padding:12px 14px;background:#f0f4ff;
                    border-left:3px solid #4a6cf7;border-radius:0 4px 4px 0;">
          <div style="font-size:11px;font-weight:700;color:#4a6cf7;text-transform:uppercase;
                      letter-spacing:.8px;margin-bottom:6px;">Executive Summary</div>
          <p style="margin:0;font-size:13px;color:#333;line-height:1.6;">{s.summary}</p>
        </div>"""

    insights_html = _insight_bullets(s.insights)

    # Plain description fallback (shown only when no AI analysis is available)
    desc_html = ""
    if not s.summary and s.description:
        short = s.description[:300] + ("…" if len(s.description) > 300 else "")
        desc_html = f'<p style="font-size:13px;color:#555;margin:8px 0 0;line-height:1.5;">{short}</p>'

    return f"""
    <tr>
      <td style="padding:20px 0;border-bottom:1px solid #eee;vertical-align:top;">
        <div style="font-size:11px;color:#888;text-transform:uppercase;
                    letter-spacing:.5px;margin-bottom:6px;">
          {s.source}&nbsp;&middot;&nbsp;{pub}
        </div>
        <a href="{s.url}"
           style="font-size:17px;font-weight:700;color:#1a1a2e;text-decoration:none;
                  line-height:1.3;">
          {s.title}
        </a>
        {desc_html}
        {summary_html}
        {insights_html}
        <div style="margin-top:12px;">
          <a href="{s.url}"
             style="font-size:12px;color:#4a6cf7;text-decoration:none;font-weight:600;">
            Read full study →
          </a>
        </div>
      </td>
    </tr>"""


def _build_html(studies: list[Study]) -> str:
    date_str = datetime.now().strftime("%B %d, %Y")
    count = len(studies)
    noun = "study" if count == 1 else "studies"
    cards = "\n".join(_study_card(s) for s in studies)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;font-family:Georgia,serif;background:#f0f2f5;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:32px 0;">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,.10);">

        <!-- Header -->
        <tr>
          <td style="background:#1a1a2e;padding:28px 36px;">
            <div style="color:#fff;font-size:22px;font-weight:700;letter-spacing:-.3px;">
              AI &amp; Workforce Studies
            </div>
            <div style="color:#8899bb;font-size:13px;margin-top:5px;">{date_str}</div>
          </td>
        </tr>

        <!-- Intro -->
        <tr>
          <td style="padding:24px 36px 8px;">
            <p style="margin:0;font-size:14px;color:#555;">
              {count} new {noun} — each with an AI-generated executive summary
              and highlighted insights for your team.
            </p>
          </td>
        </tr>

        <!-- Study cards -->
        <tr>
          <td style="padding:0 36px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {cards}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:18px 36px;background:#f9f9f9;font-size:11px;color:#aaa;
                     border-top:1px solid #eee;text-align:center;">
            AI Studies Aggregator &mdash; disable sources any time in config.yaml
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Plaintext fallback
# ---------------------------------------------------------------------------

def _build_plaintext(studies: list[Study]) -> str:
    lines = [f"AI & Workforce Studies — {datetime.now().strftime('%B %d, %Y')}", ""]
    for s in studies:
        pub = s.published.strftime("%Y-%m-%d") if s.published else "n/d"
        lines += [
            f"[{s.source}] {pub}",
            s.title,
            s.url,
        ]
        if s.summary:
            lines += ["", "Summary:", s.summary]
        if s.insights:
            lines += ["", "Key insights:"]
            lines += [f"  • {i}" for i in s.insights]
        elif s.description:
            lines.append(s.description[:300])
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------

class EmailNotifier:
    def __init__(self, cfg: dict):
        self.host = cfg["smtp_host"]
        self.port = int(cfg["smtp_port"])
        self.username = cfg["username"]
        self.password = cfg["password"]
        self.from_addr = cfg["from"]
        self.to_addr = cfg["to"]
        self.subject_prefix = cfg.get("subject_prefix", "[AI Studies]")

    def send(self, studies: list[Study]) -> None:
        if not studies:
            return

        count = len(studies)
        noun = "study" if count == 1 else "studies"
        subject = f"{self.subject_prefix} {count} new {noun}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = self.to_addr
        msg.attach(MIMEText(_build_plaintext(studies), "plain"))
        msg.attach(MIMEText(_build_html(studies), "html"))

        with smtplib.SMTP(self.host, self.port) as server:
            server.ehlo()
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.from_addr, [self.to_addr], msg.as_string())

        logger.info("Email sent: %s", subject)
