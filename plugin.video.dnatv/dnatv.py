# -*- coding: utf-8 -*-
import sys, json, time, re
import requests
from requests.auth import HTTPDigestAuth
import urlparse

testing= False

try :
	 import xbmcgui, xbmc, xbmcaddon, xbmcvfs
except:
	testing = True

class DNATVSession(requests.Session):
	def __init__(self, username, password, servicename):
		requests.Session.__init__(self)
		self.testing = testing
		if not testing:
			self.Addon = xbmcaddon.Addon(id='plugin.video.dnatv')
			self.cookies.update ({'ssid' : self.Addon.getSetting( id='ssid')})
			self.cookies.update ({'usid' : self.Addon.getSetting( id='usid')})
		else:
			self.cookies.update({'ssid':'-'})
			self.cookies.update({'usid':'-'})

		services = ['dnatv', 'booxtv']
		servicedata = [
			[{'service' : 'dnaclient', 'ver' : '0.6'},
					{'serviceUser' : 'dnaclient'},
					'https://tv.dna.fi',
					'dnaclient'],
			[{'service' : 'betaserver', 'ver' : '1.8'},
					{'serviceUser' : 'betaserver'},
					'https://webui.booxtv.fi',
					'betaserver']
			]
		self.servicedata = servicedata[services.index(servicename)]
		self.SITE = self.servicedata[2] + "/api/user/"+username
		self.loggedin = False
		self.digest_auth = HTTPDigestAuth(username, password)
		self.digest_auth.init_per_thread_state()
		loginpage = ['https://tv.dna.fi/html5/#/home', 'https://webui.booxtv.fi/webui/site/login']
		response = self.get(loginpage[services.index(servicename)])

		if username in response.text:
			self.loggedin = True

		response = self.get(self.SITE + '/recording/search?service=' + self.servicedata[3] + '&ipp=1')

		if response.status_code is 200:
			self.loggedin = True
		
		if not self.loggedin:
			# saved session already expired or logged out
			self.logentry('Needs login to booxmedia service')
			self.cookies.pop('ssid')			
			self.cookies.pop('usid')

	def login(self):
		if not self.loggedin:
			# sessionid and x-authenticate response
#			payload = {'YII_CSRF_TOKEN' : self.cookies['YII_CSRF_TOKEN'], 'ajax' : '1', 'auth_user': '1',
#				'device_id' : '1'}
			payload = {'ajax' : '1', 'auth_user': '1', 'device_id' : '1'}
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
			self.digest_auth._thread_local.chal = requests.utils.parse_dict_header(s_auth.replace('Digest ', ''))
			request = requests.Request('POST', self.SITE + '/login', data = payload)
			request.headers.update({'Authorization' : self.digest_auth.build_digest_header('POST', self.SITE + '/login')})
			prepped = self.prepare_request(request)
			response = self.send(prepped)
			if 'usid' in self.cookies:
				self.loggedin = True
				if not self.testing:
					ssid = self.Addon.setSetting( id = 'ssid', value = self.cookies.get('ssid'))
					usid = self.Addon.setSetting( id = 'usid', value = self.cookies.get('usid'))
			if self.testing:
				self.logentry(self.cookies.get('ssid'))
				self.logentry(self.cookies.get('usid'))
			self.logentry('Logged in : ' + str(self.loggedin))
		return self.loggedin
	
	def getrecordingpage(self, page):
		data = [False, None]
		pg = '&pg=' + str(page)
		tries = 0
		while tries < 5:
			try :
				et = '&et=' + str(int(time.time()))
				response = self.get(self.SITE + '/recording/search?service=' + self.servicedata[3] + et + pg)
				data = [True, response.json()]
				return data
			except:
				tries = tries + 1
				time.sleep(1)
		self.logentry('failed to get valid json data')
		return data
		
	def getrecordings(self):
		page = 0
		totalpages = ''
		data = None
		while not page == totalpages:
			page = page + 1
			if page == 1:
				recordingpage = self.getrecordingpage(page)
				if recordingpage[0]:
					data = recordingpage[1]
					totalpages = data['recordedContent']['resultSet']['totalPages']
					data = data['recordedContent']['programList']['programs']
				else:
					self.cleartemp()
					return data
			else:
				recordingpage = self.getrecordingpage(page)
				if recordingpage[0]:
					newData = recordingpage[1]['recordedContent']['programList']['programs']
					data = data + newData
				else:
					self.cleartemp()
					data = None
					return data
		cutpoint = 0
		while not data[cutpoint]['recordings']:
			cutpoint = cutpoint + 1
			continue
		return data[cutpoint:]
	
	def getlivetv(self):
		data=None
		tries = 0
		while tries < 5:
			try :
				et = '&_=' + str(int(time.time()))
				response = self.get(self.SITE + '/channel?output=full&include=epg%2Cliveservice&service=' + self.servicedata[3] +et)
				data = response.json()['channelList']['channels']
				return data
			except:
				self.logentry('failed to get valid json data')
				tries = tries + 1
				time.sleep(1)
		self.cleartemp()		
		return data
		
	def getplayableurl(self, url):
		response = self.get(url, allow_redirects=False)
		return response

	def cleartemp(self):
		self.Addon.setSetting( id='lastRecordingsRefresh', value='0')
		self.Addon.setSetting( id='recordingList', value='0')
		self.Addon.setSetting( id='lastLiveTVrefresh', value='0')
		self.Addon.setSetting( id='liveTVList', value= '0')
		self.Addon.setSetting( id='seriestitles', value='0')
		self.Addon.setSetting( id='ssid', value='0')
		self.Addon.setSetting( id='usid', value='0')


	def logout(self):
		if not self.loggedin:
			return self.loggedin
		payload = {'ajax' : '1', 'service' : self.servicedata[3]}
		response = self.post(self.SITE + '/logout', params=payload)
		if 'usid=deleted' in response.headers.get('set-cookie'):
			self.loggedin = False
			if self.testing:
				self.logentry('Logged out: ' + unicode(not self.loggedin))
			else:
				self.cleartemp()
				self.notify(self.Addon.getLocalizedString(30053) + ', ')
				xbmc.executebuiltin('xbmc.action(Back)')
				xbmc.executebuiltin('xbmc.action(Back)')
				xbmc.executebuiltin('xbmc.action(PreviousMenu)')
		else:
			if self.testing:
				self.logentry('Logged out: ' + unicode(not self.loggedin))
			else:
				self.notify(self.Addon.getLocalizedString(30054) + ', ')
		return self.loggedin

	def deleterecording(self, programid):
		self.logentry('delete recording ' + str(programid))
		payload = { 'program_uids' : str(programid), 'service' : self.servicedata[3], 'ajax' : '1'}
		response = self.delete(self.SITE + '/recording', params=payload)
		recordings = json.loads(self.Addon.getSetting( id='recordingList'))
		index = 0		
		for i in range(len(recordings)):
			if str(programid) == recordings[i]['programUid']:
				index = i
				break
		recording = recordings[index]
		start_time = recording['startTime'].split()[4][:5]
		s_time = time.strptime(recording['startTime'][:-6], '%a, %d %b %Y %H:%M:%S')
		startDate = unicode(s_time[0]) + '.' + '%02d' % (s_time[1]) + '.'  + '%02d' % (s_time[2])
		recordings.pop(index)
		self.Addon.setSetting( id='recordingList', value=json.dumps(recordings))
		if not self.testing:
			self.notify(self.Addon.getLocalizedString(30050) + ', ' + recording['title'] + ' ' + startDate + ' ' + start_time )
			xbmc.executebuiltin('XBMC.Container.Refresh')

	def downloadrecording(self, programid):
		if self.testing:
			recordings = self.getrecordings()
			dlfolder = ''
		else:
			recordings = json.loads(self.Addon.getSetting( id='recordingList'))
			dlfolder = self.Addon.getSetting( id='dlfolder')
		for recording in recordings:
			if (str(programid) in recording['programUid']) or (str(programid).lower() in recording['title'].lower()):
				self.logentry(recording['title'])
				dlurl = self.getplayableurl(recording['recordings'][1]['stream']['streamUrl']).headers.get('location')
				self.logentry(dlurl)
				start_time = recording['startTime'].split()[4][:5].replace(':','')
				s_time = time.strptime(recording['startTime'][:-6], '%a, %d %b %Y %H:%M:%S')
				startDate = unicode(s_time[0]) + '.' + '%02d' % (s_time[1]) + '.'  + '%02d' % (s_time[2])
				fOut = recording['title'] + ' ' + startDate + ' ' + start_time + '.mp4'
				fOut = re.sub('[<>"/\|?*]',"", fOut)
				fOut = dlfolder + fOut.replace(':',',')
				self.logentry(fOut)
				response = requests.get(dlurl, stream=True)
				downloadnotification = (recording['title'] + ' ' + startDate + ' ' + start_time)
				if response.status_code == 200:
					if self.testing:
						self.logentry('download started')
						with open(fOut, 'wb') as f:
							for chunk in response.iter_content(1024):
								f.write(chunk)
						self.logentry('download completed')

					else:
						self.notify(self.Addon.getLocalizedString(30051) + ', ' + downloadnotification )
						f = xbmcvfs.File(fOut, 'w')
						for chunk in response.iter_content(1024):
							f.write(chunk)
						f.close()
						self.notify(self.Addon.getLocalizedString(30052)  + ', ' + downloadnotification )

	def logentry (self, logtext):
		if self.testing:
			print logtext
		else:
			logtext = logtext.encode('utf-8')
			xbmc.log(self.Addon.getAddonInfo('name') + ': ' + logtext)

	def notify (self, notification):
		notification = notification.encode('utf-8')
		xbmc.executebuiltin('XBMC.Notification(' + notification + ')')
				
if __name__ == '__main__':
#	print str(sys.argv)

	if testing:
		print time.time()
		try:
			txt = open('login.txt')
			tsession = DNATVSession(txt.readline().strip(), txt.readline().strip(), txt.readline().strip())

		except:
			if len(sys.argv) < 4:
				sys.exit()
			tsession = DNATVSession(sys.argv[1], sys.argv[2], sys.argv[3])
	else:
		tsession = DNATVSession(sys.argv[1], sys.argv[2], sys.argv[3])		

	if tsession.login():
		if tsession.testing:
			print time.time()

		if '-delete' in sys.argv:
			tsession.deleterecording(sys.argv[sys.argv.index('-delete')+1])

		if '-download' in sys.argv:
			tsession.downloadrecording(sys.argv[sys.argv.index('-download')+1])

		if '-logout' in sys.argv or tsession.testing:
			tsession.logout() 
