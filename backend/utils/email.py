import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import GOOGLE_EMAIL, GOOGLE_PASSWORD


def send_email(send_to: str, subject: str, body: str) -> None:
    sender_email = GOOGLE_EMAIL
    password = GOOGLE_PASSWORD

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = send_to
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    try:
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, send_to, message.as_string())
    finally:
        server.quit()
