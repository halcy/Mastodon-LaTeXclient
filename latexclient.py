#/usr/bin/python3

from mastodon import Mastodon, StreamListener, CallbackStreamListener
from subprocess import call

import re
import copy
import sys

from html.parser import HTMLParser
from urllib.request import urlopen
import urllib
import html
import os
import time

POST_TEMPLATE = "\\subsection{POSTUSERNAME}\nPOSTTEXT"
IMAGE_TEMPLATE = "Figure~\\ref{figIMAGENUM}"
IMAGE_REF_TEMPLATE = "\\begin{figure}\n\\centering\n\\includegraphics[width=\\maxwidth{\\textwidth}]{IMAGEFILENAME}\n\\caption{IMAGECAPTION} \\label{figIMAGENUM}\n\\end{figure}\n"
LINK_TEMPLATE = " \\cite{ref_URLNUM} "
LINK_REF_TEMPLATE = "\\bibitem{ref_URLNUM}URLDESC, \\url{URLURL}\n"
LINK_RE = re.compile(r'(\\\\)?https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)')

def error_callback(*_, **__):
    pass

def is_string(data):
    return isinstance(data, str)

def is_bytes(data):
    return isinstance(data, bytes)

def to_ascii(data):
    if is_string(data):
        data = data.encode('ascii', errors='ignore')
    elif is_bytes(data):
        data = data.decode('ascii', errors='ignore')
    else:
        data = str(data).encode('ascii', errors='ignore')
    return data


class Parser(HTMLParser):
    def __init__(self, url):
        self.title = "No Title"
        self.rec = False
        HTMLParser.__init__(self)
        try:
            self.feed(to_ascii(urlopen(url).read()))
        except urllib.error.HTTPError:
            return
        except urllib.error.URLError:
            return
        except ValueError:
            return

        self.rec = False
        self.error = error_callback

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.rec = True

    def handle_data(self, data):
        if self.rec:
            self.title = data

    def handle_endtag(self, tag):
        if tag == 'title':
            self.rec = False


def get_title(url):
    return Parser(url).title

def tex_escape(text):
    """
        :param text: a plain text message
        :return: the message escaped to appear correctly in LaTeX
    """
    conv = {
        '&': '\\&',
        '%': '\\%',
        '$': '\\$',
        '#': '\\#',
        '_': '\\_',
        '{': '\\{',
        '}': '\\}',
        '~': '\\textasciitilde{}',
        '^': '\\^{}',
        '\\': '\\textbackslash{}',
        '<': '\\textless ',
        '>': '\\textgreater ',
    }
    regex = re.compile('|'.join(re.escape(key) for key in sorted(conv.keys(), key = lambda item: - len(item))))
    return regex.sub(lambda match: conv[match.group()], text)

def cleanhtml(raw_html):
    raw_html = raw_html.replace("</p>", "\n")
    raw_html = raw_html.replace("<br>", "\n")
    cleanr = re.compile('<.*?>')
    raw_html = html.unescape(raw_html)
    cleantext = re.sub(cleanr, '', raw_html)
    cleantext = tex_escape(cleantext)
    cleantext = cleantext.replace("\n\n", "\n")
    cleantext = cleantext.replace("\n\n", "\n")
    cleantext = cleantext.replace("\n\n", "\n")
    cleantext = cleantext.replace("\n", "\\\\")
    cleantext = cleantext.rstrip("\\\n ")
    return cleantext

link_counter = 0
links_text = ""
figure_counter = 0
def convert_tl(tl):
    global link_counter
    global links_text
    global figure_counter
    
    tl_text = ""
    for status in tl:
        status_base = copy.copy(POST_TEMPLATE)
        status_base = status_base.replace("POSTUSERNAME", status.account.display_name)
        status_base = status_base.replace("POSTTEXT", cleanhtml(status.content))
        
        link_matches = re.finditer(LINK_RE, status_base)
        for link in link_matches:
            link_counter += 1
            
            link_text = copy.copy(LINK_TEMPLATE)
            link_text = link_text.replace("URLNUM", str(link_counter))
            
            link_ref_text = copy.copy(LINK_REF_TEMPLATE)
            link_ref_text = link_ref_text.replace("URLNUM", str(link_counter))
            link_ref_text = link_ref_text.replace("URLURL", link.group(0))
            link_ref_text = link_ref_text.replace("URLDESC", tex_escape(get_title(link.group(0))))
            
            status_base = status_base.replace(link.group(0), link_text)
            links_text += link_ref_text
        
        attachments = []
        figures_text = ""
        for attachment in status.media_attachments:
            figure_counter += 1
            _, figure_ext = os.path.splitext(attachment.url)
            figure_filename = "figures/figure_" + str(figure_counter) + figure_ext
            figure_desc = "An image found on the internet."
            
            if attachment.description != None:
                figure_desc = attachment.description
            
            if figure_ext == ".png" or figure_ext == '.jpg':
                call(["wget", "-O", figure_filename, attachment.url])
                
                figure_text = copy.copy(IMAGE_REF_TEMPLATE)
                figure_text = figure_text.replace("IMAGEFILENAME", figure_filename)
                figure_text = figure_text.replace("IMAGENUM", str(figure_counter))
                figure_text = figure_text.replace("IMAGECAPTION", figure_desc)
                
                figure_ref_text = copy.copy(IMAGE_TEMPLATE)
                figure_ref_text = figure_ref_text.replace("IMAGENUM", str(figure_counter))
                
                figures_text += figure_text
                attachments.append(figure_ref_text)
            else:
                attachments.append("\\url{" + tex_escape(attachment.url) + "}")
            
        tl_text += status_base
        
        if len(attachments) != 0:
            tl_text += " (Compare " + ", ".join(attachments) + ")"
        tl_text += figures_text +"\n"
        
    return(tl_text)

api = Mastodon(
    client_id = sys.argv[2],
    access_token = sys.argv[3],
    api_base_url = sys.argv[1]
)

while(True):
    with open('samplepaper.tex', 'r') as template_file:
        latex_base = template_file.read()

    instance_info = api.instance()
    user_info = api.account_verify_credentials()

    home_tl = convert_tl(api.timeline_home())
    local_tl = convert_tl(api.timeline_local())
    fed_tl = convert_tl(api.timeline_public())

    latex_base = latex_base.replace("INSTANCENAME", instance_info.title)
    latex_base = latex_base.replace("INSTANCEURL", "https://" + instance_info.uri)
    latex_base = latex_base.replace("INSTANCEDESC", cleanhtml(instance_info.description))
    latex_base = latex_base.replace("USERNAME", user_info.acct)
    latex_base = latex_base.replace("USERURL", user_info.url)

    latex_base = latex_base.replace("HOMETL", home_tl)
    latex_base = latex_base.replace("LOCALTL", local_tl)
    latex_base = latex_base.replace("FEDTL", fed_tl)

    latex_base = latex_base.replace("LINKS", links_text)

    with open('client.tex', 'w') as output_file:
        output_file.write(latex_base)
    call(["pdflatex", "client.tex"])
    call(["pdflatex", "client.tex"])
    call(["pdflatex", "client.tex"])
    
    time.sleep(60)