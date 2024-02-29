import os
import http.client
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# get admin email list
admin_email = os.getenv("ADMIN_EMAIL")

# get server email
server_email = os.getenv("SERVER_EMAIL")
server_email_key = os.getenv("SERVER_EMAIL_KEY")

def update_dns_records():
    # get keys and ids
    dns_read_key, dns_edit_key, zone_id = get_keys()

    # set up headers
    headers = {
        'Content-Type': "application/json",
        'Authorization': "Bearer " + dns_read_key
    }

    # make request
    cf_conn.request("GET", "/client/v4/zones/" + zone_id + "/dns_records", headers=headers)

    # format response
    cf_response = cf_conn.getresponse()
    result_obj = json.loads(cf_response.read().decode("utf-8"))

    # if the request failed, don't continue
    if not result_obj["success"]:
        raise("DNS Read Error", "Something went wrong when getting the DNS records.")

    # set up connection to https://checkip.amazonaws.com
    aws_conn = http.client.HTTPSConnection("checkip.amazonaws.com")

    # make request
    aws_conn.request("GET", "/client/v4/zones/" + zone_id + "/dns_records")

    # format the response
    aws_response = aws_conn.getresponse()

    # search for an IP address
    ip_re_groups = re.search(r"([0-9]{1,3}\.){3}[0-9]{1,3}", aws_response.read().decode("utf-8"))

    # the first group should be the public IP
    current_ip = ip_re_groups.group(0)

    # loop over each DNS record
    for record in result_obj["result"]:
        # get the record's IP address
        record_ip = record["content"]

        # compare to the current IP address
        if record_ip != current_ip:
            # if different, update cloudflare
            update_dns_record(current_ip, record["name"], zone_id, record["id"], dns_edit_key)

def get_keys():
    # get the read key, edit key, and zone id
    dns_read_key = os.getenv("DNS_READ")
    dns_edit_key = os.getenv("DNS_EDIT")
    zone_id = os.getenv("ZONE_ID")

    return (dns_read_key, dns_edit_key, zone_id)

def update_dns_record(ip_address, domain_name, zone_id, dns_record_id, dns_edit_key):
    # create an argument payload
    payload = "{\n  \"content\": \"" + ip_address + "\",\n  \"name\": \"" + domain_name + "\",\n  \"proxied\": true,\n  \"type\": \"A\",\n  \"comment\": \"Domain verification record\",\n  \"ttl\": 60\n}"

    # set up headers
    headers = {
        'Content-Type': "application/json",
        'Authorization': "Bearer " + dns_edit_key
    }

    # make the request
    cf_conn.request("PATCH", "/client/v4/zones/" + zone_id + "/dns_records/" + dns_record_id, payload, headers)

    # format the response
    cf_response = cf_conn.getresponse()
    data = cf_response.read()

    # send out email
    send_email(
        "Successfully Updated DNS Record For " + domain_name,
        data.decode("utf-8").replace(",", "\n"),
        server_email,
        admin_email
    )

def send_email(subject, body, email_from, email_to):
    # set up email info
    message = MIMEMultipart()
    message['From'] = "Weld WISE Server <" + email_from + ">"
    message['To'] = email_to
    message['Subject'] = subject
    message.attach(MIMEText(body, "plain"))

    # set up secure smtp connection
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(server_email, server_email_key)

    # send the email
    server.sendmail(email_from, email_to, message.as_string())

    # slose the SMTP connection
    server.quit()

try:
    # set up connection tp API
    cf_conn = http.client.HTTPSConnection("api.cloudflare.com")

    # attempt to update dns records
    update_dns_records()
except Exception as error:
    # if anything goes wrong, send out error email
    send_email(
        "Update DNS Error",
        "An error occurred when attempting to update the DNS records:\n" + str(error),
        server_email,
        admin_email
    )