# -*- coding: utf-8 -*-
import json
import requests
from requests.auth import HTTPDigestAuth
import urlparse
import time
import sys

class DNATVSession(requests.Session):
	def __init__(self, username, password, servicename, testing = False):
		requests.Session.__init__(self)
		self.testing=testing
		if not testing:
			import xbmcgui
			import xbmcaddon
		services = ['dnatv', 'booxtv']
		servicedata = [[{'service' : 'dnaclient', 'ver' : '0.5'},
					{'serviceUser' : 'dnaclient'},
					'https://matkatv.dna.fi',
					'dnaclient'],
			{'service' : 'mobileclient', 'ver' : '1.8'},
					{},
					'https://webui.booxtv.fi',
					'mobileclient'
			]
		self.servicedata = servicedata[services.index(servicename)]
		self.SITE = self.servicedata[2] + "/api/user/"+username
		self.loggedin = False
		self.digest_auth = HTTPDigestAuth(username, password)
		loginpage = ["https://matkatv.dna.fi/webui/site/login", 'https://webui.booxtv.fi/webui/site/login']
		self.get(loginpage[services.index(servicename)])
		
	def login(self):
		# sessionid and x-authenticate response
		payload = {'YII_CSRF_TOKEN' : self.cookies['YII_CSRF_TOKEN'], 'ajax' : '1', 'auth_user': '1',
			'device_id' : '1'}
		payload.update(self.servicedata[0])
		# self.cookies.update({'lang':'fi'})
		response = self.post(self.SITE + '/login', params=payload)
		s_auth = response.headers.get('x-authenticate', '')
		# ssid
		payload2 = {'authParams': s_auth, 'uri' : self.SITE + '/login'}
		payload2.update(self.servicedata[1])
		response = self.post(self.servicedata[2] +'/auth/service', payload2 )
		# another x-authenticate response with realm="user"
		response = self.post(self.SITE + '/login', payload)
		# finally login with digest auth
		s_auth = response.headers.get('x-authenticate', '')
		self.digest_auth.chal = requests.utils.parse_dict_header(s_auth.replace('Digest ', ''))
		request = requests.Request('POST', self.SITE + '/login', data = payload)
		request.headers.update({'Authorization' : self.digest_auth.build_digest_header('POST', self.SITE + '/login')})
		prepped = self.prepare_request(request)
		response = self.send(prepped)
		if 'usid' in self.cookies:
			self.loggedin = True
		if self.testing:
			print "Logged in : " + str(self.loggedin)
		return self.loggedin

	def getrecordingpage(self, page):
		data = None
		pg = '&pg=' + str(page)
		while True:
			try :
				et = '&et=' + str(int(time.time()))
				response = self.get(self.SITE + '/recording/search?service=' + self.servicedata[3] + et + pg)
				data = response.json()
				break
			except:
				print "failed to get valid json data"
				time.sleep(1)
		return data
		
	def getrecordings(self):
		page = 0
		totalpages = ''
		data = None
		while not page == totalpages:
			page = page + 1
			if page == 1:
				data = self.getrecordingpage(page)
				totalpages = data['recordedContent']['resultSet']['totalPages']
				data = data['recordedContent']['programList']['programs']
			else:
				newData = self.getrecordingpage(page)['recordedContent']['programList']['programs']
				data = data + newData
		cutpoint = 0
		while not data[cutpoint]['recordings']:
			cutpoint = cutpoint + 1
			continue
		return data[cutpoint:]
	
	def getlivetv(self):
		data=None
		while True:
			try :
				et = '&_=' + str(int(time.time()))
				response = self.get(self.SITE + '/channel?output=full&include=epg%2Cliveservice&service=' + self.servicedata[3] +et)
				data = response.json()
				break
			except:
				print "failed to get valid json data"
				time.sleep(1)
		return data['channelList']['channels']
		
	def getplayableurl(self, url):
		response = self.get(url, allow_redirects=False)
		return response

	def logout(self):
		if not self.loggedin:
			return self.loggedin
		payload = {'ajax' : '1', 'service' : self.servicedata[3]}
		response = self.post(self.SITE + '/logout', params=payload)
		if 'usid' not in self.cookies:
			self.loggedin = False
		if self.testing:
			print "Logged out: " + str(not self.loggedin)
		return self.loggedin

if __name__ == '__main__':
	print str(sys.argv)
	print time.time()
	testsession = DNATVSession(sys.argv[1], sys.argv[2], sys.argv[3], True)
	if testsession.login():
		print time.time()
		testsession.getrecordings()		
		print time.time()
		testsession.logout()
