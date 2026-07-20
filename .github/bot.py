import datetime
import os
import xml.etree.ElementTree as ET

FEED_FILE = "feed.xml"

# Test-Daten (wird später durch echte X-Posts ersetzt)
post_text = "Testbeitrag von @moscht_coc"
post_url = "https://x.com/moscht_coc"

now = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")

ET.SubElement(channel, "title").text = "Moscht X Feed"
ET.SubElement(channel, "link").text = "https://x.com/moscht_coc"
ET.SubElement(channel, "description").text = "Automatischer Feed für Discord"

item = ET.SubElement(channel, "item")

ET.SubElement(item, "title").text = post_text
ET.SubElement(item, "description").text = post_text
ET.SubElement(item, "link").text = post_url
ET.SubElement(item, "pubDate").text = now

tree = ET.ElementTree(rss)
tree.write(FEED_FILE, encoding="utf-8", xml_declaration=True)

print("RSS Feed erstellt")
