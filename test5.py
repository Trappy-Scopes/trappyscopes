
destination= "yatharth.bhasin@gimm.pt"
server= "smtp.mailersend.net"
port= 587
username= "MS_7l9jSQ@trial-pq3enl6opw5l2vwr.mlsender.net"
password = "rwEzS8SrVhBrIJgD"
recipient_email = "yatharth1997@gmail.com"
import smtplib
from email.mime.text import MIMEText

sender_email = "MS_7l9jSQ@trial-pq3enl6opw5l2vwr.mlsender.net"
#sender_password = "password"
recipient_email = destination
subject = "[Trappy-Scopes Autobot] Hello!"
body = """
Hello Yatharth,

These are we, the Trappy-Scopes. We have taken over.

-XOXO
The Trappy-Scopes
"""
html_message = MIMEText(body, 'html')
html_message['Subject'] = subject
html_message['From'] = sender_email
html_message['To'] = recipient_email
# Try to send the email
try:
    with smtplib.SMTP(server, port) as server:
        server.starttls()  # Secure the connection
        server.login(username, password)  # Login with MailerSend credentials
        server.sendmail(sender_email, recipient_email, html_message.as_string())  # Send the email
        
    print("Email sent successfully!")
    
except Exception as e:
    print(f"Failed to send email: {e}")