# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# imdb.py
# Copyright (C) 2020 Fracpete (fracpete at gmail dot com)

from bs4 import BeautifulSoup
import json
import logging
import os
import requests
from time import sleep
from xml.dom import minidom
from kodi.xml_utils import add_node

# logging setup
logger = logging.getLogger("kodi.imdb")

def getActorThumb(aID, language): # returns actor thumb url for the specified IMDB actor ID.
    sleep(1)
    aID = aID.strip(" /")

    # generate URL
    if aID.startswith("http"):
        url = aID
    else:
        url = "https://www.imdb.com/name/%s/" % aID
    logger.info("IMDB actor URL: " + url)

    # retrieve html
    r_actor = requests.get(url, headers={"Accept-Language": language})
    if r_actor.status_code != 200:
        logging.critical("Failed to retrieve actor URL (status code %d): %s" % (r_actor.status_code, url))

    # parse html
    soupActor = BeautifulSoup(r_actor.content, "html.parser")
    try:
        thumb = soupActor.find('img', id='name-poster')['src']
    except: thumb = ""
    return thumb

def generate_imdb(id, language="en", fanart="none", fanart_file="folder.jpg", nfo_file=None):
    """
    Generates the XML for the specified IMDB ID.

    :param id: the IMDB ID to use
    :type id: str
    :param language: the preferred language for the titles
    :type language: str
    :param fanart: how to deal with fanart
    :type fanart: str
    :param fanart_file: the fanart filename to use (when downloading or re-using existing)
    :type fanart_file: str
    :param nfo_file: the current nfo full file path
    :type nfo_file: str
    :return: the generated XML DOM
    :rtype: minidom.Document
    """

    id = id.strip()

    # generate URL
    if id.startswith("http"):
        url = id
    else:
        url = "https://www.imdb.com/title/%s/" % id
    logger.info("IMDB URL: " + url)


    # retrieve html
    r = requests.get(url, headers={"Accept-Language": language})
    if r.status_code != 200:
        logging.critical("Failed to retrieve URL (status code %d): %s" % (r.status_code, url))

    # parse html
    soup = BeautifulSoup(r.content, "html.parser")

    titleStoryline = soup.find("div", id="titleStoryLine")
    try: tagline = titleStoryline.find("h4", string="Taglines:").parent.contents[2].strip()
    except: tagline = ""
    try: plot = titleStoryline.find_all("div")[0].find_all("span")[0].string.strip()
    except: plot = ""

    titleDetails = soup.find("div", id="titleDetails")
    try: countries = titleDetails.find("h4", string="Country:").parent.find_all("a")
    except: countries = []
    try: studios = titleDetails.find("h4", string="Production Co:").parent.find_all("a")
    except: studios = []

    titleCast = soup.find("table", class_="cast_list")
    try: cast = titleCast.find_all("tr", class_=['odd', 'even'])
    except: cast = []
        
    doc = minidom.Document()

    widget = soup.find("div", id="star-rating-widget")
    preflang_title = widget["data-title"]

    for script in soup.findAll("script", type="application/ld+json"):
        j = json.loads(script.text)
        logger.debug(j)

        root = add_node(doc, doc, "movie")
        add_node(doc, root, "title", preflang_title)
        add_node(doc, root, "originaltitle", j["name"])
        uniqueid = add_node(doc, root, "uniqueid", j["url"].replace("/title/", "").replace("/", ""))
        uniqueid.setAttribute("type", "imdb")
        uniqueid.setAttribute("default", "true")
        if "description" in j:
            add_node(doc, root, "outline", j["description"])
        if plot !="":
            add_node(doc, root, "plot", plot)
        if "datePublished" in j:
            add_node(doc, root, "premiered", j["datePublished"])
        if "director" in j and "name" in j["director"]:
            add_node(doc, root, "director", j["director"]["name"])
        if "genre" in j:
            if isinstance(j["genre"], list):
                for genre in j["genre"]:
                    add_node(doc, root, "genre", genre)
            else:
                add_node(doc, root, "genre", j["genre"])
        if "trailer" in j and "embedUrl" in j["trailer"]:
            add_node(doc, root, "trailer", "https://www.imdb.com" + j["trailer"]["embedUrl"])
        if "aggregateRating" in j and "ratingValue" in j["aggregateRating"]:
            xratings = add_node(doc, root, "ratings")
            xrating = add_node(doc, xratings, "rating")
            xrating.setAttribute("name", "imdb")
            xrating.setAttribute("max", "10")
            add_node(doc, xrating, "value", j["aggregateRating"]["ratingValue"])

#        fanart_file = os.path.basename(nfo_file)[:-4] + ".jpg"
        if fanart == "download":
            if "image" in j:
                logger.info("Downloading fanart: %s" % j["image"])
                r = requests.get(j["image"], stream=True)
                if r.status_code == 200:
                    fanart_path = os.path.join(os.path.dirname(nfo_file), fanart_file)
                    with open(fanart_path, 'wb') as f:
                        for chunk in r:
                            f.write(chunk)
                    xthumb = add_node(doc, root, "thumb", fanart_file)
                    xthumb.setAttribute("aspect", "poster")
                else:
                    logger.critical("Failed to download fanart, status code: " % r.status_code)
            else:
                logger.warning("No image associated, cannot download!")
        elif fanart == "use-existing":
            xthumb = add_node(doc, root, "thumb", fanart_file)
            xthumb.setAttribute("aspect", "poster")
        else:
            logger.critical("Ignoring unhandled fanart type: %s" % fanart)

    for actor in cast:
        xactor = add_node(doc, root, "actor")

        aname = actor.find_all("td")[1].find("a").string.strip()
        add_node(doc, xactor, "name", aname)

        try:
            alink = actor.select("td.primary_photo>a[href^='/name']")[0]
            if alink.find('img').has_attr('loadlate'):
                aphoto = getActorThumb(alink['href'].split('/name/')[1], language)
                add_node(doc, xactor, "thumb", aphoto)
        except: pass

    if tagline !="":
        add_node(doc, root, "tagline", tagline)
    for country in countries:
        add_node(doc, root, "country", country.string.strip())
    for studio_ in studios:
        studio = studio_.string.strip()
        if studio != "See more":
            add_node(doc, root, "studio", studio)

    return doc
