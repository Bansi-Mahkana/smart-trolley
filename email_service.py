import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import Config

logger = logging.getLogger(__name__)


def send_receipt_email(customer_email, customer_name, transaction_id, items, total_amount):
    """
    Sends a styled HTML receipt email to the customer for a completed transaction.

    :param customer_email: Recipient's email address
    :param customer_name: Recipient's full name
    :param transaction_id: ID or reference of the transaction
    :param items: List of dicts representing purchased items (product_name/name, quantity/qty, unit_price/price, subtotal)
    :param total_amount: Total transaction amount
    :return: True if the email was sent successfully, False otherwise
    """
    if not customer_email:
        logger.warning("Receipt email not sent: No customer email provided.")
        return False

    current_date = datetime.now().strftime("%B %d, %Y %I:%M %p")

    # Build plain text alternative
    text_lines = [
        "Smart Trolley - Shopping Receipt",
        "=" * 40,
        f"Customer Name  : {customer_name}",
        f"Transaction ID : #{transaction_id}",
        f"Date           : {current_date}",
        "-" * 40,
        f"{'Item':<20} {'Qty':<5} {'Price':<8} {'Subtotal':<8}",
        "-" * 40,
    ]

    table_rows_html = []
    for item in items:
        name = item.get('product_name') or item.get('name', 'Unknown')
        qty = item.get('quantity') or item.get('qty', 1)
        price = float(item.get('unit_price') or item.get('price', 0.0))
        subtotal = float(item.get('subtotal', qty * price))

        text_lines.append(f"{name[:19]:<20} {qty:<5} Rs.{price:<7.2f} Rs.{subtotal:<7.2f}")
        table_rows_html.append(f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px 12px; font-size: 14px; color: #1e293b;">{name}</td>
                <td style="padding: 10px 12px; font-size: 14px; color: #1e293b; text-align: center;">{qty}</td>
                <td style="padding: 10px 12px; font-size: 14px; color: #1e293b; text-align: right;">Rs. {price:.2f}</td>
                <td style="padding: 10px 12px; font-size: 14px; color: #1e293b; text-align: right; font-weight: 600;">Rs. {subtotal:.2f}</td>
            </tr>
        """)

    text_lines.extend([
        "-" * 40,
        f"Total Amount   : Rs.{float(total_amount):.2f}",
        "=" * 40,
        "Thank you for shopping with Smart Trolley!",
    ])
    plain_text = "\n".join(text_lines)

    # Build styled HTML receipt
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Trolley - Shopping Receipt</title>
</head>
<body style="margin: 0; padding: 20px 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); border: 1px solid #e2e8f0;">
        <!-- Header -->
        <tr>
            <td style="background: linear-gradient(135deg, #2563eb, #1d4ed8); padding: 28px 24px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -0.5px;">Smart Trolley - Shopping Receipt</h1>
                <p style="color: #bfdbfe; margin: 6px 0 0 0; font-size: 14px;">Instant Checkout & Automated Billing</p>
            </td>
        </tr>

        <!-- Receipt Info -->
        <tr>
            <td style="padding: 24px 28px 16px 28px;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                        <td style="font-size: 14px; color: #64748b; line-height: 1.6;">
                            <strong style="color: #1e293b; font-size: 15px;">Billed To:</strong><br>
                            <span style="color: #0f172a; font-weight: 600;">{customer_name}</span><br>
                            {customer_email}
                        </td>
                        <td style="font-size: 14px; color: #64748b; line-height: 1.6; text-align: right; vertical-align: top;">
                            <strong style="color: #1e293b; font-size: 15px;">Receipt Details:</strong><br>
                            Transaction ID: <span style="color: #0f172a; font-weight: 600;">#{transaction_id}</span><br>
                            Date: {current_date}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- Itemized Table -->
        <tr>
            <td style="padding: 0 28px 16px 28px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin-top: 8px;">
                    <thead>
                        <tr style="background-color: #f1f5f9; border-top: 1px solid #e2e8f0; border-bottom: 2px solid #cbd5e1;">
                            <th style="padding: 10px 12px; font-size: 13px; font-weight: 600; color: #475569; text-align: left;">Item</th>
                            <th style="padding: 10px 12px; font-size: 13px; font-weight: 600; color: #475569; text-align: center;">Qty</th>
                            <th style="padding: 10px 12px; font-size: 13px; font-weight: 600; color: #475569; text-align: right;">Unit Price</th>
                            <th style="padding: 10px 12px; font-size: 13px; font-weight: 600; color: #475569; text-align: right;">Subtotal</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(table_rows_html)}
                    </tbody>
                </table>
            </td>
        </tr>

        <!-- Total Box -->
        <tr>
            <td style="padding: 8px 28px 24px 28px;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top: 2px dashed #cbd5e1; padding-top: 12px;">
                    <tr>
                        <td style="font-size: 18px; font-weight: 700; color: #0f172a; padding: 8px 0;">Total Amount</td>
                        <td style="font-size: 22px; font-weight: 800; color: #2563eb; text-align: right; padding: 8px 0;">Rs. {float(total_amount):.2f}</td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- Footer -->
        <tr>
            <td style="background-color: #f8fafc; padding: 20px 24px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="margin: 0; font-size: 15px; font-weight: 600; color: #1e293b;">Thank you for shopping with Smart Trolley!</p>
                <p style="margin: 6px 0 0 0; font-size: 12px; color: #94a3b8;">This is an automated receipt generated by your IoT Smart Trolley System.</p>
            </td>
        </tr>
    </table>
</body>
</html>"""

    # Assemble MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Smart Trolley - Shopping Receipt #{transaction_id}"
    msg["From"] = Config.SMTP_FROM_EMAIL
    msg["To"] = customer_email

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    # Check if SMTP credentials / server are configured
    if not Config.SMTP_SERVER:
        logger.warning("SMTP server not configured in Config.")
        return False

    try:
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()

        if Config.SMTP_USERNAME and Config.SMTP_PASSWORD:
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)

        server.send_message(msg)
        server.quit()
        logger.info("Receipt email sent successfully to %s for transaction #%s", customer_email, transaction_id)
        return True
    except Exception as e:
        logger.error("Failed to send receipt email to %s: %s", customer_email, e)
        return False
