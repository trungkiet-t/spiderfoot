# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_dehashed
# Purpose:      Spiderfoot plugin to gather compromised emails, 
#               passwords, hashes, and other data from Dehashed.
#
# Author:      Krishnasis Mandal <krishnasis@hotmail.com>
#
# Created:     02/05/2020
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

from sflib import SpiderFoot, SpiderFootPlugin, SpiderFootEvent
import base64
import json

class sfp_dehashed(SpiderFootPlugin):
    
    """Dehashed:Footprint,Investigate,Passive:Leaks and Breaches:apikey:Gather compromised emails, passwords, hashes and other data"""
    opts = {
        'email': '',
        'api_key': '',
        'max_pages' : ''
    }

    # Option descriptions. Delete any options not applicable to this module.
    optdescs = {
        'email': "Email for accessing Dehashed API",
        'api_key': "Dehashed API Key.",
        'max_pages': "Maximum number of pages to query"
    }

    # Tracking results can be helpful to avoid reporting/processing duplicates
    results = None

    # Tracking the error state of the module can be useful to detect when a third party
    # has failed and you don't wish to process any more events.
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc

        self.results = self.tempStorage()

        # Clear / reset any other class member variables here
        # or you risk them persisting between threads.

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    # For a list of all events, check sfdb.py.
    def watchedEvents(self):
        return ['EMAILADDR']

    # What events this module produces
    def producedEvents(self):
        return ["EMAILADDR_COMPROMISED", "PASSWORD_COMPROMISED",
                "HASH_COMPROMISED", "RAW_RIR_DATA"]

    # When querying third parties, it's best to have a dedicated function
    # to do so and avoid putting it in handleEvent()
    def query(self, qry, currentPage):
        b64_auth = base64.b64encode((self.opts['email'] + ":" + self.opts['api_key']).encode("utf-8"))
        headers = {
            'Accept' : 'application/json',
            'Authorization': "Basic " + b64_auth.decode("utf-8")
        }
        self.sf.debug(str(headers))        
        res = self.sf.fetchUrl("https://api.dehashed.com/search?query=\"" + qry + "\"" + "&page=" + str(currentPage),
                                headers=headers,
                                timeout=15,
                                useragent=self.opts['_useragent'])
        
        self.sf.debug(str(res))
        self.sf.debug("CONTENT : ::::::::" + str(res.get('content')))
        if res.get('code') == '401':
            return None
        if res.get('content') is None:
            self.sf.debug("No Dehashed info found for " + qry)
            return None

        # Always always always process external data with try/except since we cannot
        # trust the data is as intended.
        try:
            info = json.loads(res.get('content'))
        except Exception as e:
            self.sf.error("Error processing JSON response from Dehashed.", False)
            return None

        return info

    # Handle events sent to this module
    def handleEvent(self, event):
        self.sf.debug("Testing Dehashed . ")
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        # Once we are in this state, return immediately.
        if self.errorState:
            return None

        # Log this before complaining about a missing API key so we know the
        # event was received.
        self.sf.debug("Received event, " + eventName + ", from " + srcModuleName)

        # Always check if the API key is set and complain if it isn't, then set
        # self.errorState to avoid this being a continual complaint during the scan.
        if self.opts['api_key'] == "" or self.opts['email'] == "":
            self.sf.error("You enabled sfp_dehashed but did not set an email or API key!", False)
            self.errorState = True
            return None
        

        # Don't look up stuff twice
        if eventData in self.results:
            self.sf.debug("Skipping " + eventData + " as already mapped.")
            return None

        self.results[eventData] = True

        # To implement  : Number of pages 
        # Fetch Dehashed data for incoming data (email)
        self.sf.debug("Starting querying from DeHashed")
        currentPage = 1
        entries = list()
        self.sf.debug("Current Page : " + str(currentPage))
        self.sf.debug("Max Pages : " + self.opts['max_pages'])
        while currentPage <= int(self.opts['max_pages']):
            self.sf.debug("Looking for page : " + str(currentPage))
            jsonData_temp = self.query(eventData, currentPage)
            if jsonData_temp is None: 
                self.sf.error("No Data receieved")
                break
            else:  
                self.sf.debug("Received : " + str(entries))
                entries.append(jsonData_temp.get('entries'))
            # Dehashed returns 5000 results for each query
            if len(entries) >= 5000 * currentPage:
                currentPage += 1
            else:
                break
        
        if entries is None:
            return None

        
        evt.moduleDataSource = event.moduleDataSource

        breachSource = ""
        email = ""
        password = ""
        hashed_password = ""
        emails = list()
        passwords = list()
        hashed_passwords = list()

        for entry in entries:
            # If email does not exist or is null
            if entry.get('email') is None or str(entry.get('email')).strip() == '':
                continue

            if not (entry.get('obtained_from') is None or str(entry.get('obtained_from')).strip() == ''):
                breachSource = entry.get('obtained_from')
            
            email = entry.get('email')
            emails.append(email + " : " + "[" + breachSource + "]")

            # Check if password exists 
            if not (entry.get('password') is None or str(entry.get('password')).strip() == ''):
                password =  entry.get('password')
                passwords.append(email + " : " + password + " [" + breachSource + "]")

            # Check if hashed_password exists
            if not entry.get('hashed_password') is None or str(entry.get('hashed_password')).strip() == '':
                hashed_password = entry.get('hashed_password')

                if not (len(password) == 0 or password is None):
                    hashed_passwords.append(email + " : " + hashed_password + "(Password : " + password + ") [" + breachSource + "] ")
                else:
                    hashed_passwords.append(email + " : " + hashed_password + " [ " + breachSource + "]")

            # Pass the JSON object as RAW_RIR_DATA 
            evt = SpiderFootEvent("RAW_RIR_DATA", str(entry), self.__name__, event)
            self.notifyListeners(evt)

        # Send the events to the listener
        for email in emails:
            evt = SpiderFootEvent("EMAILADDR_COMPROMISED", email, self.__name__, event)
            self.notifyListeners(evt)

        for password in passwords:
            evt = SpiderFootEvent("PASSWORD_COMPROMISED", password, self.__name__, event)
            self.notifyListeners(evt)

        for hashed_password in hashed_passwords:
            evt = SpiderFootEvent("HASH_COMPROMISED", hashed_password, self.__name__, event)
            self.notifyListeners(evt)
        
            
        if self.checkForStop():
            return None
            
        return None

# End of sfp_dehashed class
