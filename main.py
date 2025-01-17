#!/usr/bin/python3
from email.mime.application import MIMEApplication

import requests
import json
import re
import smtplib
import ssl
import logging
import sys
import os.path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config
from bs4 import BeautifulSoup


DOWNLOAD_PDF_BUTTON_CLASS = "liste1"
PDF_FILENAME = "grades.pdf"

def login(session):
    params = (
        ('state', 'user'),
        ('type', '1'),
        ('category', 'auth.login'),
        ('re', 'last'),
        ('startpage', 'portal.vm'),
    )

    data = {
        'username': Config.user,
        'password': Config.pwd,
        'submit': 'Anmelden'
    }

    response = session.post(
        'https://basis.uni-bonn.de/qisserver/rds', params=params, data=data)

    soup = BeautifulSoup(response.text, 'html.parser')
    aas = soup.find("a", text="Notenspiegel")
    return aas.attrs["href"]


def navigateToGradeTable(session, notenlink):
    response = session.get(notenlink)
    soup = BeautifulSoup(response.text, 'html.parser')
    imgs = soup.find_all("img", src="/QIS/images//information.svg")
    return [x.parent.attrs["href"] for x in imgs]


def navigateToCorrectGradeTableAndIterateTableCells(session, gradeLink, filterstr):
    response = session.get(gradeLink)
    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find_all("table")[1]
    rows = []
    logging.debug("filter: " + filterstr)
    for row in table.find_all("tr"):
        tds_text = [td.text.strip() for td in row.find_all("td")]
        if len(tds_text) >= 2 and filterstr in tds_text[1]:
            rows.append(tds_text)
    return rows


def wrapWithTD(string):
    return '<td style="padding-right: 1em;">' + string + "</td>"


def sendMail(subject, rows, pdfContent):
    context = ssl.create_default_context()
    message = MIMEMultipart()
    message["Subject"] = subject
    message["From"] = Config.mail["from"]
    message["To"] = Config.mail["to"]
    html = "<html><body><table>"
    for row in rows:
        try:
            html += "<tr>" + wrapWithTD(row[1]) + wrapWithTD(row[2]) + wrapWithTD(
                row[3]) + wrapWithTD(row[4]) + wrapWithTD(row[5]) + wrapWithTD(row[9]) + "</tr>"
        except:
            # if the row was malformed -> ignore it
            pass
    html += "</table></body></html>"
    htmlPart = MIMEText(html, 'html')
    message.attach(htmlPart)

    pdfAttachment = MIMEApplication(pdfContent, Name=PDF_FILENAME)
    pdfAttachment['Content-Disposition'] = f'attachment; filename="{PDF_FILENAME}"'
    message.attach(pdfAttachment)

    with smtplib.SMTP(Config.smtpServer, Config.smtpServerPort) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(Config.mail["from"], Config.mail["fromPwd"])
        server.set_debuglevel(1)
        server.sendmail(Config.mail["from"],
                        Config.mail["to"], message.as_string())


def downloadPdf(session, url):
    response = session.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    createPdfButton = soup.find("a", {"class": DOWNLOAD_PDF_BUTTON_CLASS})
    pdfLink = createPdfButton["href"]

    downloadPdfResponse = session.get(pdfLink)
    return downloadPdfResponse.content


if __name__ == "__main__":
    logging.basicConfig(filename='app.log', filemode='w',
                        format='%(name)s - %(levelname)s - %(message)s')
    session = requests.Session()
    notenlink = login(session)

    for gradeTable in Config.gradeTables:
        logging.debug("==================================================")
        #logging.debug("Updating studies: "+gradeTable["gradeTableNum"]+" with filename "+gradeTable["filename"])
        logging.debug("==================================================")
        grade_links = navigateToGradeTable(session, notenlink)
        currentGradeTableLink = grade_links[gradeTable["gradeTableNum"]]

        rows = navigateToCorrectGradeTableAndIterateTableCells(session, currentGradeTableLink, "")
        if os.path.isfile(gradeTable["filename"]):
            with open(gradeTable["filename"]) as f:
                data = json.load(f)
        else:
            data = []

        if data != rows:
            logging.debug("not equal")
            pdfContent = downloadPdf(session, currentGradeTableLink)
            sendMail("Update to your grades [" + gradeTable["userFriendlyName"] + "]", rows, pdfContent)
        else:
            logging.debug("equal")
        with open(gradeTable["filename"], "w") as text_file:
            text_file.write(json.dumps(rows))
