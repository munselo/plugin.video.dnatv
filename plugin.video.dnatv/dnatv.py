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
			settings = xbmcaddon.Addon(id='plugin.video.dnatv')
			self.cookies.update ({'ssid' : settings.getSetting( id='ssid')})
			self.cookies.update ({'usid' : settings.getSetting( id='usid')})
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
		loginpage = ['https://tv.dna.fi/webui/site/login', 'https://webui.booxtv.fi/webui/site/login']
		response = self.get(loginpage[services.index(servicename)])

		if username in response.text:
			self.loggedin = True
		else:
			# saved session already expired or logged out
			print 'Needs login to booxmedia service'
			self.cookies.pop('ssid')			
			self.cookies.pop('usid')

	def login(self):
		if not self.loggedin:
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
			self.digest_auth._thread_local.chal = requests.utils.parse_dict_header(s_auth.replace('Digest ', ''))
			request = requests.Request('POST', self.SITE + '/login', data = payload)
			request.headers.update({'Authorization' : self.digest_auth.build_digest_header('POST', self.SITE + '/login')})
			prepped = self.prepare_request(request)
			response = self.send(prepped)
			if 'usid' in self.cookies:
				self.loggedin = True
				if not self.testing:
					settings = xbmcaddon.Addon(id='plugin.video.dnatv')
					ssid = settings.setSetting( id = 'ssid', value = self.cookies.get('ssid'))
					usid = settings.setSetting( id = 'usid', value = self.cookies.get('usid'))
			if self.testing:
				print self.cookies.get('ssid')
				print self.cookies.get('usid')
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
		if not self.testing:
			import xbmcaddon
			settings = xbmcaddon.Addon(id='plugin.video.dnatv')
		if 'usid=deleted' in response.headers.get('set-cookie'):
			self.loggedin = False
			if self.testing:
				print "Logged out: " + str(not self.loggedin)
			else:
				xbmc.executebuiltin("XBMC.Notification(" + settings.getLocalizedString(30053) + ", " + ")")
		else:
			if self.testing:
				print "Logged out: " + str(not self.loggedin)
			else:
				xbmc.executebuiltin("XBMC.Notification(" + settings.getLocalizedString(30054) + ", " + ")")
		return self.loggedin

	def deleterecording(self, programid):
		print "delete recording " + str(programid)
		payload = { 'program_uids' : str(programid), 'service' : self.servicedata[3], 'ajax' : '1'}
		response = self.delete(self.SITE + '/recording', params=payload)
		import xbmcaddon
		settings = xbmcaddon.Addon(id='plugin.video.dnatv')
		recordings = json.loads(settings.getSetting( id='recordingList'))
		index = 0		
		for i in range(len(recordings)):
			if str(programid) == recordings[i]['programUid']:
				index = i
				break
		recording = recordings[index]
		start_time = recording['startTime'].split()[4][:5]
		s_time = time.strptime(recording['startTime'][:-6], '%a, %d %b %Y %H:%M:%S')
		startDate = str(s_time[0]) + '.' + '%02d' % (s_time[1]) + '.'  + '%02d' % (s_time[2])
		deletenotification = (recording['title'] + ' ' + startDate + ' ' + start_time).encode('utf-8')
		recordings.pop(index)
		settings.setSetting( id='recordingList', value=json.dumps(recordings))
		if not self.testing:
			xbmc.executebuiltin("XBMC.Notification(" + settings.getLocalizedString(30050).encode('utf-8') + ", " + deletenotification + ")")
			xbmc.executebuiltin('XBMC.Container.Refresh')

	def downloadrecording(self, programid):
		if self.testing:
			recordings = self.getrecordings()
			dlfolder = ''
		else:
			settings = xbmcaddon.Addon(id='plugin.video.dnatv')
			recordings = json.loads(settings.getSetting( id='recordingList'))
			dlfolder = settings.getSetting( id='dlfolder')
		for recording in recordings:
			if (str(programid) in recording['programUid']) or (str(programid).lower() in recording['title'].lower()):
				print recording['title'].encode('utf-8')
				dlurl = self.getplayableurl(recording['recordings'][1]['stream']['streamUrl']).headers.get('location')
				print dlurl
				start_time = recording['startTime'].split()[4][:5].replace(':','')
				s_time = time.strptime(recording['startTime'][:-6], '%a, %d %b %Y %H:%M:%S')
				startDate = str(s_time[0]) + '.' + '%02d' % (s_time[1]) + '.'  + '%02d' % (s_time[2])
				fOut = recording['title'] + ' ' + startDate + ' ' + start_time + '.mp4'
				fOut = re.sub('[<>"/\|?*]',"", fOut)
				fOut = dlfolder + fOut.replace(':',',')
				fOut = fOut.encode('utf-8')
				print fOut
				response = requests.get(dlurl, stream=True)
				downloadnotification = (recording['title'] + ' ' + startDate + ' ' + start_time).encode('utf-8')
				if response.status_code == 200:
					if self.testing:
						print 'download started'
						with open(fOut, 'wb') as f:
							for chunk in response.iter_content(1024):
								f.write(chunk)
						print 'download completed'

					else:
						note = (", ").encode('utf-8') + downloadnotification + (")").encode('utf-8')
						xbmc.executebuiltin("XBMC.Notification(" + settings.getLocalizedString(30051).encode('utf-8') + note )
						f= xbmcvfs.File(fOut, 'w')
						for chunk in response.iter_content(1024):
							f.write(chunk)
						f.close()
						xbmc.executebuiltin("XBMC.Notification(" + settings.getLocalizedString(30052).encode('utf-8') + note )
				
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
