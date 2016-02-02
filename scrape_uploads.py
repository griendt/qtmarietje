#!/usr/bin/env python2

import sys, urllib, urllib2, cookielib, re, getpass, os

class MarietjeScraper:
	def __init__(self, username, password):
		self.username = username
		self.password = password

	def refresh_uploader_info(self):
		cj = cookielib.CookieJar()
		opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
		login_data = urllib.urlencode({'login' : self.username, 'password' : self.password})
		resp = opener.open('http://noordslet.science.ru.nl/login.php', login_data)
		if 'Could not login.' in resp.read():
			print 'Could not refresh uploads, wrong username or password.'
			return False
		resp = opener.open('http://noordslet.science.ru.nl/request.php')
		text = resp.read()

		regex = ur"<tr.*name='(\d+)'.*\n.*\n(.*?)</td>"
		tracks_array = re.findall(regex, text)
		tracks_array.sort(key=lambda x: int(x[0]))

		tracks = []
		for track in tracks_array:
			tracks.append(track[0] + ': ' + track[1] + '\n')
		f = open('uploader_info.txt','w')
		f.writelines(tracks)
		f.close()
		print 'Done refreshing uploads.'
		return True

def main(argv):
	username = ''
	password = ''
	if os.path.exists("username"):
		with open("username",'r') as f:
			lines = f.read().splitlines()
			line_count = len(lines)
			if(line_count > 1):
				username = lines[0]
				password = lines[1]

	if len(username) < 1 or len(password) < 1:
		username = raw_input("Enter username: ")
		password = getpass.getpass("Enter password: ")

	scraper = MarietjeScraper(username, password)
	scraper.refresh_uploader_info()


if __name__ == '__main__':
	main(sys.argv)