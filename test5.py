


from rayoptics.environment import *
import matplotlib.pyplot as plt

def draw_lens_system(lenses, distances):
    # Create optical model
    opm = OpticalModel()
    sm = opm['seq_model']
    
    # Set system properties
    opm.optical_spec.pupil = PupilSpec(opm.optical_spec, value=10, 
                                      key=['object', 'pupil'], 
                                      type=DimensionType.Radius)
    
    # Add object plane
    sm.add_surface()
    sm.ifcs[0].label = "Object"
    sm.gaps[0].thi = 0  # Start immediately after object
    
    # Add lenses and distances
    z = 0
    for i, (lens, distance) in enumerate(zip(lenses, distances)):
        # Add distance before lens
        if i > 0:
            sm.gaps[i].thi = distance
            z += distance
        
        # Add lens surface
        s = sm.add_surface()
        s.label = lens
        s.profile = Spherical(c=0)  # Flat surface for simplicity
        s.interact_mode = 'reflect' if 'M' in lens else 'transmit'
        
        # Set aperture size
        sm.ifcs[i+1].max_aperture = 10
    
    # Add image plane
    sm.add_surface()
    sm.ifcs[-1].label = "Image"
    sm.gaps[-1].thi = 0
    
    # Update model
    opm.update_model()
    
    # Create diagram
    plt.figure(FigureClass=InteractiveLayout, opt_model=opm,
               do_draw_rays=False, do_paraxial_layout=True,
               is_dark=False)
    plt.title('Lens System Diagram')
    plt.tight_layout()
    plt.show()

# Example usage
lenses = ['L1', 'M1', 'L2', 'L3']  # Lens names (M for mirrors)
distances = [20, 30, 40]            # Distances between elements
draw_lens_system(lenses, distances)

raise KeyboardInterrupt



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