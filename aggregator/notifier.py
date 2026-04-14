import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .models import Study

logger = logging.getLogger(__name__)


def _build_html(studies: list[Study]) -> str:
    date_str = datetime.now().strftime("%B %d, %Y")
    rows = []
    for s in studies:
        pub = s.published.strftime("%Y-%m-%d") if s.published else "Unknown date"
        desc = s.description[:400] + "…" if len(s.description) > 400 else s.description
        rows.append(f"""
        <tr>
          <td style="padding:12px 0; border-bottom:1px solid #eee; vertical-align:top;">
            <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">
              {s.source} &middot; {pub}
            </div>
            <a href="{s.url}" style="font-size:16px;font-weight:600;color:#1a1a2e;text-decoration:none;">
              {s.title}
            </a>
            {"<p style='font-size:13px;color:#555;margin:6px 0 0;'>" + desc + "</p>" if desc else ""}
          </td>
        </tr>""")

    items_html = "\n".join(rows)
    count = len(studies)
    noun = "study" if count == 1 else "studies"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:Georgia,serif;background:#f5f5f5;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:30px 0;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1);">
        <tr>
          <td style="background:#1a1a2e;padding:24px 32px;">
            <div style="color:#fff;font-size:20px;font-weight:700;letter-spacing:-.3px;">
              AI &amp; Workforce Studies
            </div>
            <div style="color:#aaa;font-size:13px;margin-top:4px;">{date_str}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px;">
            <p style="margin:0 0 20px;font-size:14px;color:#555;">
              {count} new {noun} found across your monitored sources.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0">
              {items_html}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 32px;background:#f9f9f9;font-size:11px;color:#aaa;
                     border-top:1px solid #eee;text-align:center;">
            AI Studies Aggregator &mdash; unsubscribe by disabling sources in config.yaml
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_plaintext(studies: list[Study]) -> str:
    lines = [f"AI & Workforce Studies — {datetime.now().strftime('%B %d, %Y')}", ""]
    for s in studies:
        pub = s.published.strftime("%Y-%m-%d") if s.published else "n/d"
        lines.append(f"[{s.source}] {pub}")
        lines.append(s.title)
        lines.append(s.url)
        if s.description:
            lines.append(s.description[:300])
        lines.append("")
    return "\n".join(lines)


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
