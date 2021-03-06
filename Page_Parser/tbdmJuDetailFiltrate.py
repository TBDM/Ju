#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Filtrate data from Ju detail pages.

########################################
#               WARNING                #
########################################
# Your HTML files must be list like this:
#   root/         
#   ...
#       tbdm/
#       ...
#           file/
#           ...
#               20170526/
#                   success/
#                   error/
#                   success.log
#               20170525/
#               20170524/
#               20170523/
#               ...
# 
# 
# Set the global variable fileLocation 
# as '/root/tbdm/file/'
########################################
#               WARNING                #
########################################

#----------model import----------

import os
import sys
import re
import json

from lxml import etree

#----------model import----------
sys.path.append('../')
from Scaffold.tbdmLogging import tbdmLogger

#----------global variables----------

parseLog = tbdmLogger('./Logs/parse_ju_log', loglevel = 30).log

#----------function definition----------

def parseJuDetailPage(htmlStr, htmlName, juDetailXpath):
    try:
        treeObj = etree.HTML(htmlStr)
    except Exception as e:
        juDetailResult['error'] = ['html error']
        juDetailResult['ju_id'] = htmlName.split('-')[1]
        juDetailResult['item_id'] = htmlName.split('-')[2]
        juDetailResult['timestamp'] = htmlName.split('-')[3][:-5]
        return juDetailResult

    # Here we get a HTML tree so that we can use xpath to find the element we need.
    juDetailResult['error'] = list()
    for info in juDetailXpath:
        # Find the information we need via the dict we declared.
        isMatched = False
        # Once we find the information, set the isMatched as True and then break out of the loop.
        for i in range(len(juDetailXpath[info]['xpath'])):
            # Find a useful xpath to get the information we need.
            resultList = treeObj.xpath(juDetailXpath[info]['xpath'][i])
            # The if statements below are used to make sure we match the right element as we predicted.
            if(len(resultList) != 0):
                if(juDetailXpath[info]['only'][i]):
                    if(len(resultList) == 1 and resultList[0] != ''):
                        juDetailResult[info] = resultList[0]
                        isMatched = True
                else:
                    juDetailResult[info] = resultList
                    isMatched = True
            if(isMatched):
                break
        if(not(info in juDetailResult) and not(juDetailXpath[info]['option'])):
            # The information we need but can not be found in juDetailResult
            # So there must be some errors.
            if(info == 'ju_price'):
                # when the price is not an integer xpath can not match the right price
                # so we need to use regular expression to get the price.
                
                ########################################
                #               WARNING                #
                ########################################
                # watch out for the error IndexError.

                juPriceRawStr = re.search('<span class="J_actPrice">([\S]+)</span>', htmlStr).group(0)
                juPriceStr = juPriceRawStr.replace('<i>', '').replace('</i>', '').replace('<span class="J_actPrice">', '').replace('</span>', '')
                juDetailResult['ju_price'] = juPriceStr
                continue

                ########################################
                #               WARNING                #
                ########################################
            
            # print the information for debuging.
            juDetailResult['error'].append(info)
    
    # Do not forget to set ju_id and item_id **and timestamp**that are stored in the filename.
    juDetailResult['ju_id'] = htmlName.split('-')[1]
    juDetailResult['item_id'] = htmlName.split('-')[2]
    juDetailResult['timestamp'] = htmlName.split('-')[3][:-5]
    
    # Here we have parsed all the useful data
    # What we need to do next is to clean the data
    
    # From:     \n title \n
    # To:       title
    juDetailResult['title'] = juDetailResult['title'].strip()

    # From:     background-image: url(head_picture_url);
    # To:       head_picture_url
    if(juDetailResult['head_picture'][0:16] == 'background-image'):
        juDetailResult['head_picture'] = juDetailResult['head_picture'][22:-2]

    # From:     ms
    # To:       s
    if('start_time' in juDetailResult):
        juDetailResult['start_time'] = juDetailResult['start_time'][0:10]

    # From:     \n ju_price \n
    # To:       ju_price
    juDetailResult['ju_price'] = juDetailResult['ju_price'].strip()
    
    # From:     ¥origin_price
    # To:       origin_price
    if('origin_price' in juDetailResult):
        juDetailResult['origin_price'] = juDetailResult['origin_price'][1:]

    # From:     ['rate ↑', 'rate -', 'rate ↓']
    # To:       [['rate', '1'], ['rate', '0'], ['rate','-1']
    for i in range(3):
        if(juDetailResult['seller_rate'][i][-1:] == '↑'):
            juDetailResult['seller_rate'][i] = [juDetailResult['seller_rate'][i][0:-2], '1']
        if(juDetailResult['seller_rate'][i][-1:] == '-'):
            juDetailResult['seller_rate'][i] = [juDetailResult['seller_rate'][i][0:-2], '0']
        if(juDetailResult['seller_rate'][i][-1:] == '↓'):
            juDetailResult['seller_rate'][i] = [juDetailResult['seller_rate'][i][0:-2], '-1']

    return juDetailResult

#----------function definition----------


#----------main function----------

if __name__ == "__main__":
    if(not len(sys.argv[2:])):
        print('Usage: '+sys.argv[0]+' [origin file] [outfile]')
        sys.exit(0)
    fileLocation = sys.argv[1]
    fileName = sys.argv[2]
    with open('ju_xpath.json', 'r', encoding='utf-8') as f:
        juDetailXpath = json.load(f)
    result  = []
    with open(fileName, 'w') as f:
        for date in os.listdir(fileLocation):
            print(date)
            # Filtrate the page day by day.
            if(os.path.isdir(fileLocation + date) and len(date) == 8 and re.match('^([0-9]{8})$', date)):
                # Only if the path is a direction and the folder name is like YYYYMMDD can it be parsed.
                for juPage in os.listdir(fileLocation + date + '/success/'):
                    juDetailResult = dict()
                    # the dict juDetailResult is used to store the content we parsed temporarily.
                    if(juPage[0:8] == 'juDetail'):
                        # Ju detail page will be named like juDetail-JuID-ItemID-Timestrap.html
                        pageObj = open(fileLocation + date + '/success/' + juPage, 'r', encoding='UTF-8')
                        pageStr = pageObj.read()
                        result.append(parseJuDetailPage(pageStr, juPage, juDetailXpath))
                        if(len(result) > 1000):
                            for i in range(len(result)):
                                f.write(json.dumps(result[i], ensure_ascii=False) + '\n')
                            result = []
                    else:
                        continue
        for i in range(len(result)):
            f.write(json.dumps(result[i], ensure_ascii=False) + '\n')