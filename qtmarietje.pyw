#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

from __future__ import with_statement
import os
import sys
import socket
import threading
import time
import logging
import random
import optparse
import getpass
import matplotlib
matplotlib.use("Qt4Agg")


from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg
import matplotlib.pyplot as plt
try: import eyed3
except: pass

import marietje

try: import pylast
except: pass

from scrape_uploads import MarietjeScraper


#############################################################
#
#   PyQt Marietje Client
#   (c) 2015 Alex van de Griendt
#
#   Based on original RawMarietje class by Bas Westerbaan
#
#   
#   Features:
#   - look up queue and database
#   - request tracks under username
#   - look up song id by special query
#   - query randomly selected track
#   - highlight tracks that have been queued previously
#   - upload tracks
#   - detects song metadata when uploading
#
#	Changes in version 0.09:
#	- added checkbox to turn on/off notifications
#	- own queue time display
#	- error message when trying to queue when queue time is full
#	- case is ignored when checking for duplicates when uploading
#	- notifies user when upload is successful
#
#   Changes in version 0.08:
#   - dunst notification option
#   - fixed graph drawing error
#
#   Changes in version 0.06:
#   - better support for scrolling in queue;
#   - #TODO: still some minor issues present.
#
#   Changes in version 0.051:
#   - minor bugfixes in graph update and display
#
#
#   Changes in version 0.05:
#   - added plot that shows total queue time (blue)
#	 and user queue time (green) over time in minutes.
#
#   Changes in version 0.04:
#   - remembers upload folder for consecutive uploads
#   - checks if song already exists prior to uploading
#   - highlight tracks (red) that are already in queue
#   - highlight tracks (yellow) that are queued by Marietje
#   - highlight tracks (green) that you currently have in queue
#   - fixed double use of timers that caused a core to max out
#
#   Future Plans:
#   - last.fm integrity (scrobbling)
#   - last.fm now_playing artist information display
#   - random statistics about current queue
#   - os.getlogin() only works on UNIX systems
#
#
#############################################################

m = marietje.RawMarietje()

M_VERSION = "0.09"

FormClass, BaseClass = uic.loadUiType("ui.ui")

class MainWindow(FormClass, BaseClass):
	def __init__(self,user,mainobj):
		BaseClass.__init__(self)
		self.setupUi(self)
		self.notification_checkbox.setCheckState(2)
		self.user = user
		
		self.setWindowTitle("QtMarietje %s - Logged in as %s" % (M_VERSION, self.user))
		self.setWindowIcon(QIcon("icon.ico"))
		self.setMinimumSize(800,400)
		self.mainobj = mainobj  # global object
		self.queued_ids = self.get_queued_songs()
		self.time_left = 0
		self.dir_name = ''
		self.selectedUploader= u''

		self.systemTray = QSystemTrayIcon(QIcon("icon.ico"),self)
		self.systemTray.show()

		self.timer = QTimer(self)
		self.timer.start(950)   # refresh now_playing time

		# help messagebox
		self.messagebox = QMessageBox(self)
		self.messagebox.setWindowTitle("QtMarietje v{0} Help".format(M_VERSION))
		self.messagebox.setText("PyQt4 based Marietje client version {0} <br>".format(M_VERSION)+
		"(c) 2015, Alex van de Griendt<br><br>"+
		"<u>Hotkeys:</u><br>"+
		"<b>F1</b>: Set focus on the query bar for user input<br>"+
		"<b>F2</b>: Show this help file<br>"+
		"<b>F3</b>: Insert a random track into the user input<br>"+
		"<b>F4</b>: Upload a new track to the database<br>"+
		"<b>F5</b>: Refetch the track database<br>"+
		"<b>F6</b>: Refetch the queue<br>"+
		"<b>F7</b>: Reset the graph<br>"+
		"<b>F8</b>: Push \"Now playing\" notification<br>"+
		"<b>F12</b>: Quit<br><br<br>"+
		"<u>Instructions:</u><br>"+
		"Use the arrow keys at any moment to focus on the table.<br>"+
		"Press <i>Enter</i> while having a song selected to request.<br>"+
		"Start a query with \"id:\" to search for the song with specified track ID.<br><br>"+
		"The blue curve in the graph represents the total queue time, the green curve the total queue time by the user."+
		"The songs that are listed under Marietje do not count towards queue time.<br><br>"+
		"<u>Color Legend:</u> (from low to high priority)<br>"+
		"<font color=#28A828><b>Green:</b> Song is in queue and requested by current user</color><br>"+
		"<font color=#8888F8><b>Blue:</b> Song has been queued on this system before</color><br>"+
		"<font color=#A8A828><b>Yellow:</b> Song was already suggested by Marietje (but may be requested)</color><br>"+
		"<font color=#A82828><b>Red:</b> Song is already in queue by a user</color><br>")
		
		self.error_box = QMessageBox(self)
		self.error_box.setWindowTitle("Error!")
		self.error_box.setText("Max queue length exceeded!")
		#self.setCentralWidget(self.table)
		
		

		self.statuslabel = QLabel(self)
		self.statusbar.addPermanentWidget(self.statuslabel)
	   
		# plot
		
		self.statplot = MatplotlibWidget(self)
		self.statplot.setFixedWidth(160)
		self.statplot.setFixedHeight(150)
		self.statplot.move(640,250)
		self.layout_vr.addWidget(self.statplot)
		self.plotpoints = []
		self.plotpoints_user = []
		self.plotpoints_marietje = []
		#self.statplot.xlabel('x?')
		#text = "Logged in as <b>{0}</b><br><b>F2</b>: Show Help".format(self.user)
		text = "bla"
		self.label_user.setText(text)

		# signals
		self.suggestions = []
		self.query_bar.textChanged.connect(self.perform_query)
		self.query_bar.returnPressed.connect(self.request_track)
		self.fill_uploader_box()
		self.comboUploaders.currentIndexChanged.connect(self.uploader_set)
		self.resetUploader.clicked.connect(lambda: self.comboUploaders.setCurrentIndex(-1))
		self.queue_table = QueueTable(self,dict(),user)

		self.random = self.button_random.clicked.connect(self.random_query)
		self.upload = self.button_upload.clicked.connect(self.upload_track)
		self.requested_track = self.table.doubleClicked.connect(self.request_track)
		self.timer_fired = self.timer.timeout.connect(self.timer2_refresh)
		
		self.actionAbout.triggered.connect(self.messagebox.show)
		self.actionExit.triggered.connect(lambda: sys.exit(0))
		self.actionRandom_Song.triggered.connect(self.random_query)
		self.actionUpload_Track.triggered.connect(self.upload_track)
		self.actionChange_User.triggered.connect(self.change_user)

		self.upload_thread = None

		QTimer.singleShot(2000,self.notifyMessage)

		self.lastfm_username.setText("Last.fm Username")
		self.lastfm_password.setText("Password")
		self.lastfm_password.setEchoMode(QLineEdit.Password)
		self.lastfm_username.setStyleSheet("background:#F0F0F0")
		self.lastfm_password.setStyleSheet("background:#F0F0F0")
		
		self.lastfm_password.returnPressed.connect(self.lastfm_login)
		self.lastfm_loginbutton.clicked.connect(self.lastfm_login)
		self.lastfm_loggedin = False
		self.lastfm_scrobblecheck.setCheckState(0)
		self.lastfm_scrobblecheck.stateChanged.connect(self.lastfm_switch_scrobbling)
		
		self.lastfm_blacklistbutton.clicked.connect(self.lastfm_blacklist)
		with open("blacklist",'r') as f:
			blacklist = eval("['"+f.read()+"']".replace(",","','"))
			print("Blacklist: "+str(blacklist))
			f.close()
	'''def resizeEvent(self,resizeEvent):
		h = self.geometry().height()
		self.button_random.move(5,305-400+h)
		self.button_upload.move(105,305-400+h)
		self.label.move(5,355-400+h)
		self.query_bar.move(5,335-400+h)
		self.queue_table.setMaximumHeight(280-400+h)
	'''

	def lastfm_login(self):
		if self.lastfm_loggedin:
			self.lastfm_loggedin = False
			self.lastfm_username.setStyleSheet("background:#F0F0F0")
			self.lastfm_password.setStyleSheet("background:#F0F0F0")
			self.lastfm_loginbutton.setText("Login to Last.fm")
			return
		password_hash = pylast.md5(self.lastfm_password.text())
		try:
			self.lastfm_loginbutton.setText("Logging in...")
			self.network = pylast.LastFMNetwork(api_key="1a8078aea8442f92c98755e29e24f4cf",api_secret="cdf440e7b9ebef25087253b8ee64d604",username=self.lastfm_username.text(),password_hash=password_hash)
			self.lastfm_username.setStyleSheet("background:#28a828")
			self.lastfm_password.setStyleSheet("background:#28a828")
			self.lastfm_loginbutton.setText("Logout")
			print("Login to Last.fm successful!")
			self.lastfm_loggedin = True
		except pylast.WSError:
			print("Authentication failed: wrong login")
			errorbox = QMessageBox(self)
			errorbox.setWindowTitle("Authentication failed")
			errorbox.setText(u"Login failed! You have entered incorrect user details.")
			errorbox.show()
		except:
			print("Authentication failed: unknown error")
			errorbox = QMessageBox(self)
			errorbox.setWindowTitle("Authentication failed")
			errorbox.setText(u"Login failed! An unknown error occurred.")
			errorbox.show()
		return
		
	def lastfm_switch_scrobbling(self):
		if self.lastfm_scrobblecheck.isChecked():
			if not self.lastfm_loggedin:
				warningbox = QMessageBox(self)
				warningbox.setWindowTitle("Log in to Last.fm")
				warningbox.setText(u"Scrobbling only works after logging in to Last.fm. Enter your credentials into the client to enable scrobbling.")
				warningbox.show()
		return
		
	def lastfm_blacklist(self):
		try:
			with open("blacklist",'r') as f:
				blacklist = f.read()
				print(blacklist)
				f.close()
		except:
			blacklist = ""
			
		(blacklist,ok) = QInputDialog.getText(self,"Update Blacklist","Artists corresponding to a Blacklist entry will never be scrobbled. Use commas to seperate entries. Use the escape character \\, if necessary.",QLineEdit.Normal,str(blacklist))
		if not ok: return
		with open("blacklist",'w') as f:
			f.write(blacklist)
			f.close()
		return
	
	def change_user(self):
		(user,ok) = QInputDialog.getText(self,"Change Username","Username:",QLineEdit.Normal,self.user)
		if not ok: return
		while not m.check_login(user):
			(user,ok) = QInputDialog.getText(self,"Username not known","Username:",QLineEdit.Normal,self.user)
			if not ok: return
		self.user = user
		self.queued_ids = self.get_queued_songs()
		self.setWindowTitle("QtMarietje %s - Logged in as %s" % (M_VERSION, self.user))
		self.timer_refresh()
		

	def get_queued_songs(self):
		queued_ids = []
		try:
			with open('uploads_%s' % self.user,'r') as f:
				for line in f:
					queued_ids.append(int(line.rstrip()))
				f.close()
			return queued_ids
		except:
			print("Could not find or load uploads.")

	def fill_uploader_box(self):
		self.comboUploaders.clear()
		self.comboUploaders.addItem(u"")
		for u in m.uploaders:
			self.comboUploaders.addItem(unicode(u))

	def uploader_set(self,i):
		if i==-1:
			u = u""
		else:
			u = self.comboUploaders.currentText()
		self.selectedUploader = u
		self.perform_query()

	def notifyMessage(self):
		if not self.notification_checkbox.isChecked():
			return
		if os.name != 'nt':
			os.system('notify-send -u "low" "Marietje" "Now Playing: {0}"'.format(self.currentSong))
		else:
			self.systemTray.showMessage("Marietje",u"Currently Playing: " + self.currentSong)

	def timer_refresh(self):
		'''Refreshes the screen every 20 seconds to update the queue if the query is empty.'''
		if self.query_bar.text() == '' and not self.selectedUploader:
			queue = m.get_queue()
			
			time_left = queue[0]
			data = []
			for a,s,l,r in queue[1]:
				a = a.decode("utf-8")
				s = s.decode("utf-8")
				data.append((a,s,l,r))
			self.queue_data = dict(enumerate([list(data[i]) for i in xrange(len(data))]))
			self.refresh(self.queue_data,dtype='queue')
		
		(np_id, stamp, length, time) = m.get_playing()
		self.time_left = stamp - time + length
		for key in self.data.keys():
			if self.data[key][0]==np_id:
				np = str(self.data[key][1]) + " - " + str(self.data[key][2])
				break
		else:
			np = ''
			print "No song appears to be playing!"

		mn, se = divmod(int(self.time_left),60)
		ho, mn = divmod(mn, 60)
		tl_formatted = "{0}:{1}:{2}".format(str(ho),str(mn).zfill(2),str(se).zfill(2))
		self.label3.setText("now playing: <b>"+np+"</b> (<i>"+tl_formatted+"</i>)")
		self.np_id = np_id

	def timer2_refresh(self):
		'''Refreshes the screen every second to update the np timer only.'''
		self.time_left -=1
		if int(self.time_left/10)*10 == self.time_left or self.time_left<=0:	# refresh timers every 5 seconds
			#print("Automatic timer refresh (every 10 seconds).")		  
			self.timer_refresh()
			return
		for key in self.data.keys():
			if self.data[key][0]==self.np_id:
				np = self.data[key][1] + u" - " + self.data[key][2]
				self.currentSong = np

		if self.time_left == 1:
			if self.lastfm_loggedin and self.lastfm_scrobblecheck.isChecked(): # scrobble track when it finishes
				try:
					(np_id, stamp, length, tim) = m.get_playing()
					for key in self.data.keys():
						if self.data[key][0]==np_id:
							np = self.data[key][1] + u" - " + self.data[key][2]
							artist = self.data[key][1]
							title = self.data[key][2]
					#track = self.network.get_track(artist=self.data[key][1],title=self.data[key][2])
					try:
						with open("blacklist",'r') as f:
							blacklist = eval("['"+f.read()+"']").replace(",","','")
							f.close()
					except:
						print("Blacklist file doesn't exist or is corrupt!")
						blacklist = []
					print(blacklist)
					if not artist in blacklist:
						self.network.scrobble(artist=artist,title=title,timestamp=time.time())
				except BaseException as e:
					print(e)
					raise
			
			QTimer.singleShot(6000,self.notifyMessage)

		mn, se = divmod(int(self.time_left),60)
		ho, mn = divmod(mn, 60)
		tl_formatted = "{0}:{1}:{2}".format(str(ho),str(mn).zfill(2),str(se).zfill(2))
		self.label3.setText(u"now playing: <b>"+np+u"</b> (<i>"+tl_formatted+u"</i>)")
		

		
		if len(self.query_bar.text())<3 and not self.selectedUploader:
			self.refresh(self.queue_data,dtype='queue')
			self.plotpoints.append(self.queue_table.totaltime/60. - self.queue_table.totaltime_marietje/60. + self.time_left/60.)
			self.plotpoints_user.append(self.queue_table.totaltime_user/60.)
			secs = int((self.plotpoints_user[-1] - int(self.plotpoints_user[-1]))*60)
			if secs<10: secs = "0"+str(secs)
			else: secs = str(secs)

			if self.plotpoints_user[-1] < 20:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#000080><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))
			elif self.plotpoints_user[-1] < 30:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#28A828><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))
			elif self.plotpoints_user[-1] < 45:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#A8A828><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))
			else:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#A82828><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))

		else:
			self.plotpoints.append(self.plotpoints[-1] - 1/60.)
			self.plotpoints_user.append(max(0,self.plotpoints_user[-1]-1/60.))
			self.label_user.setText("??")
			secs = int((self.plotpoints_user[-1] - int(self.plotpoints_user[-1]))*60)
			if secs<10: secs = "0"+str(secs)
			else: secs = str(secs)
			if self.plotpoints_user[-1] < 20:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#000080><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))
			elif self.plotpoints_user[-1] < 30:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#28A828><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))
			elif self.plotpoints_user[-1] < 45:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#A8A828><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))
			else:
				self.label_user.setText("Logged in as <b>{0}</b><br><b>F2</b>: Show Help<br>Queue Time: <font color=#A82828><b>{1}:{2}</b></color>".format(self.user,int(self.plotpoints_user[-1]),secs))
				'''if self.queue_table.queue_empty:
				self.plotpoints_marietje.append(self.plotpoints_marietje[-1]-1/60.)
			else:
				self.plotpoints_marietje.append(self.plotpoints_marietje[-1])'''

		if len(self.plotpoints) > 1:
			self.statplot.axis.clear()
			self.statplot.axis.set_xlim(0,len(self.plotpoints)/60. +5)
			self.statplot.axis.set_ylim(0,max(self.plotpoints)+5)
			self.statplot.axis.plot([i/60. for i in range(len(self.plotpoints)-1)],self.plotpoints[1:])
			self.statplot.axis.plot([i/60. for i in range(len(self.plotpoints_user)-1)],self.plotpoints_user[1:])
			#self.statplot.axis.plot([i/60. for i in range(len(self.plotpoints_marietje)-1)],self.plotpoints_marietje[1:])
			#self.statplot.axis.set_yticklabels(yticks)
			self.statplot.canvas.draw()
		self.timer.stop()
		self.timer.start()

	def perform_query(self):
		'''Look at query and update the table accordingly.'''
		query = self.query_bar.text()
		if not query and not self.selectedUploader: # show queue
			self.refresh(self.queue_data,dtype='queue')
			return
			
		suggestions = {}

		if unicode(query).startswith("id:") and len(query)>3:
			for song in self.data:
				if self.data[song][0] == int(query[3:]):
					suggestions[song] = self.data[song]
		else:
			for song in self.data:
				v = self.data[song][1] + u" " + self.data[song][2]
				if unicode(query).lower() in v.lower():
					if not self.selectedUploader or self.selectedUploader == self.data[song][3]:
						suggestions[song]=self.data[song]

		self.suggestions = suggestions

		if not unicode(query).startswith("id:") and len(suggestions) < 1000:
			self.artists = self.count_artists(self.suggestions)
		elif unicode(query).startswith("id:"):
			self.artists = int(suggestions!=dict())

		if len(suggestions) < 1000:
			self.refresh(self.suggestions)
			if not len(suggestions) == 1: 
				self.statuslabel.setText(u"<b>{0}</b> results found. <b>{1}</b> unique artists found.".format(len(suggestions),self.artists))
			else: self.statuslabel.setText(u"<b>1</b> result found. Press <i>Enter</i> to request.")
		else:
			self.refresh(self.queue_data,dtype='queue')
			if not query=='':
				self.statuslabel.setText(u"Too many (<b>{0}</b>) query results to show!".format(len(suggestions)))
			else: 
				if self.plotpoints_user[-1] > 45:
					self.error_box.show()
					return
				if self.statuslabel.text()==u"Request successful!":
					self.timer_refresh()
					pass
				else: 
					text = "<b>{0}</b> total tracks in database. <b>{1}</b> Total artists found (<b>{2:.2f}</b> songs per artist).".format(len(suggestions),self.total_artists,float(len(suggestions)/float(self.total_artists)))
					self.statuslabel.setText(text)
		return
	
	def count_artists(self,suggestions):
		self.suggestions_artists = []
		for key in suggestions.keys():
			if suggestions[key][1] not in self.suggestions_artists:
				self.suggestions_artists.append(suggestions[key][1])
		return(len(self.suggestions_artists))

	def random_query(self):
		key = random.choice(self.data.keys())
		query = unicode(self.data[key][1]) + u" " + str(self.data[key][2])
		self.query_bar.setText(query)

	def request_track(self):
		index = self.table.selectedIndexes()
		print(len(index))
		if not len(index)==1:
			self.statusbar.showMessage("No unique song selected!",5000)
		else:
			track_id = int(self.table.model().data(index[0]).toString())
			if self.plotpoints_user[-1] > 45:
				self.error_box.show()
				return
			else:
				self.error_box.show()
				print("!!")
			m.request_track(track_id,self.user)
			self.statusbar.showMessage("Request successful!",5000)

	def upload_track(self):
		if self.upload_thread != None:
			QMessageBox.warning(self,"Already Uploading","We are already uploading a track. Please Wait")
			return
		dialogbox = QFileDialog(self)
		dialogbox.setDirectory(self.dir_name)
		file_path = dialogbox.getOpenFileName(self,"Select Track",self.dir_name,"Media Files (*.*)")
		if not file_path.isEmpty():
			self.dir_name = str(file_path)
		if file_path=='': return
		try:
			af = eyed3.load(str(file_path))
			af_artist = af.tag.artist
			af_title = af.tag.title
		except:
			print("Could not detect metadata.")
			af_artist = ''
			af_title = ''
		if not af_artist: af_artist = ''
		if not af_title: af_title = ''
		(artist,ok) = QInputDialog.getText(self,"Upload Track","Artist Name:",QLineEdit.Normal,af_artist)
		if not ok: return
		(song,ok) = QInputDialog.getText(self,"Upload Track","Song Name:",QLineEdit.Normal,af_title)
		if not ok: return
		print (unicode(artist),unicode(song))

		for key in self.data.keys():
			if self.data[key][1].lower() == artist.toLower() and self.data[key][2].lower() == song.toLower():
				errorbox = QMessageBox(self)
				errorbox.setWindowTitle("Track already exists")
				errorbox.setText(u"A song with id <b>{0}</b> already exists with<br>".format(self.data[key][0])+
				u"Artist: <b>{0}</b><br>Title: <b>{1}</b><br><br>Upload will be aborted.".format(artist,song))
				errorbox.show()
				return

		self.upload_song = u"%s - %s" % (unicode(artist),unicode(song))
		self.statusbar.showMessage(u"Uploading %s. Progress: 0.0%%" % self.upload_song)
		
		QApplication.processEvents()
		QApplication.processEvents()
		self.upload_thread = UploadThread(unicode(artist).encode("utf-8"),unicode(song).encode("utf-8"),self.user,file_path)
		self.upload_thread.finished.connect(self.uploaded_track)
		self.upload_thread.progress.connect(self.upload_progress)
		self.upload_thread.start()

	def switch_kantine(self):
		pass
	
	def upload_progress(self,progress):
		if progress < 0.99:
			self.statusbar.showMessage(u"Uploading %s. Progress: %.1f%%" % (self.upload_song,progress*100),100)
		else:
			self.statusbar.showMessage(u"Uploading %s. Processing..." % self.upload_song)

	def uploaded_track(self):
		newt = self.upload_thread.duration
		self.statusbar.showMessage("Upload successful after {0:.4f} seconds".format(newt),10000)
		print("Upload successful!")
		self.upload_thread.finished.disconnect()
		self.upload_thread.progress.disconnect()
		self.upload_thread = None
		
		if not self.notification_checkbox.isChecked():
			return
		if os.name != 'nt':
			os.system('notify-send -u "low" "Marietje" "Upload successful!"')
		else:
			self.systemTray.showMessage("Marietje",u"Upload successful!")

	def refresh(self,data,dtype='database'):
		if self.table.selectedIndexes():
			selectedrow = self.table.selectedIndexes()[0].row()
		else: selectedrow = 1
		#scrolly = self.queue_table.scrollbar.value()
		#scrollvalue = self.queue_table.scrollbar.value()
		#self.queue_table.setParent(None) # old table gets removed by Python garbage collector
		if len(data)==0:
			if dtype=='database':
				self.queue_table.update_table(dict(),['Track ID','Artist','Song','Uploaded By'])
			elif dtype=='queue':
				self.queue_table.update_table(self.queue_data,['1','2','3','4'])
			else:
				print("Unknown table format")
				return
		else:
			if dtype=='database':
				self.queue_table.update_table(data,['Track ID','Artist','Song','Uploaded By'])
			elif dtype=='queue':
				self.queue_table.update_table(data,['Artist','Song','Plays In','By'],dtype='queue',time=self.time_left)
		#self.queue_table.move(5,25)
		#self.setCentralWidget(self.queue_table)
		#self.layout.addWidget(self.queue_table,0,0)
	
		#if selectedrow + 1 == len(data):	   # strange scroll display bug fix when selected row is second to last ???
		#   self.queue_table.scrollbar.setValue(9999)
		#else: self.queue_table.scrollbar.setValue(scrolly)  # ensure proper scrolling thing
		self.table.selectRow(selectedrow)

		if dtype=='database':
			try:
				for i in xrange(len(self.data)):
					queued = False
					if int(self.table.item(i,0).text()) in self.queued_ids:
						for j in range(4):
							self.table.item(i,j).setBackground(QColor(220,220,250))
							self.table.item(i,j).setForeground(QColor(160,160,250))
							queued = True
					for key in self.queue_data.keys():
						if self.table.item(i,1).text()==self.queue_data[key][0] and \
						self.table.item(i,2).text()==self.queue_data[key][1]:
							if str(self.queue_data[key][3])=="marietje":
								for j in range(4):
									self.table.item(i,j).setBackground(QColor(250,250,180))
									self.table.item(i,j).setForeground(QColor(250,250,60))
							else:
								for j in range(4):
									self.table.item(i,j).setBackground(QColor(168,40,40)) #A82828
									self.table.item(i,j).setForeground(QColor(50,0,0))
			except: pass	# queue_table may be empty

		if dtype=='queue':
			try:
				for key in self.queue_data.keys():
					if str(self.queue_data[key][3])==self.user:
						for j in range(4):
							self.table.item(int(key),j).setBackground(QColor(150,250,150))
							self.table.item(int(key),j).setForeground(QColor(10,40,10))
			except: pass
							
	
	def keyPressEvent(self, event):
		''' Global keypress handler.'''
		if type(event) == QKeyEvent:
			if event.key() in [Qt.Key_Down,Qt.Key_Up,Qt.Key_Left,Qt.Key_Right]:
				self.table.setFocus()
			elif event.key() == Qt.Key_Return:
				if not self.table.selectedIndexes():
					return
				if self.comboUploaders.hasFocus():
					return
				if not self.query_bar.text() and not self.selectedUploader:
					return
				index = self.table.selectedIndexes()[0]
				track_id = int(self.table.model().data(index).toString())
				try:
					if self.plotpoints_user[-1] > 45:
						self.error_box.show()
						return
					m.request_track(track_id,self.user)

					self.statusbar.showMessage("Request successful!",5000)
					self.query_bar.setFocus()
					self.queued_ids.append(track_id)
					self.timer_refresh()
				except: pass				
				self.query_bar.setText("")
				self.comboUploaders.setCurrentIndex(0)
				self.comboUploaders.setEditText(u"")
				self.uploader_set(0)
			elif event.key() in [Qt.Key_F1]:
				self.query_bar.setFocus()
			elif event.key() == Qt.Key_F5:
				t = time.time()
				print("Fetching songs...")
				self.statusbar.showMessage("Fetching songs...")
				QApplication.processEvents()
				QApplication.processEvents()
				try:
					self.data = fetch_songs()
					newt = time.time() - t
					self.statusbar.showMessage("Fetching completed in {0:.4f} seconds.".format(newt),5000)
					self.fill_uploader_box()
				except:
					self.statusbar.showMessage("ERROR: Fetching database failed.",10000)
				self.query_bar.setText('')
				self.perform_query()
			elif event.key() == Qt.Key_F6:
				t = time.time()
				self.statusbar.showMessage("Fetching queue...")
				QApplication.processEvents()
				QApplication.processEvents()
				try:
					self.timer_refresh()
					newt = time.time() - t
					self.statusbar.showMessage("Fetching completed in {0:.4f} seconds.".format(newt),5000)
				except:
					self.statusbar.showMessage("ERROR: Fetching queue failed.",10000)
			elif event.key() == Qt.Key_F7:
				self.plotpoints = []
				self.plotpoints_user = []
				self.plotpoints_marietje = []
			elif event.key() == Qt.Key_F8:
				self.notifyMessage()
			elif event.key() == Qt.Key_F12:
				sys.exit(0)

class QueueTable(object):
	def __init__(self, parent, data, user):
		self.parent = parent
		self.table = self.parent.table
		self.data = data
		self.user = user
		self.update_table(self.data,['Track ID','Artist','Song','Uploaded By'])
		self.format_table(self.data)
		self.totaltime = 0
		self.totaltime_marietje = 0
		self.queue_empty = True

	def format_time(self,time):
		mn, se = divmod(int(time),60)
		ho, mn = divmod(mn, 60)
		tl_formatted = u"{0}:{1}:{2}".format(str(ho),str(mn).zfill(2),str(se).zfill(2))
		return(tl_formatted)

	def update_table(self,data,header,dtype='database',time=0):
		self.table.clear()
		self.table.setColumnCount(len(header))
		self.table.setRowCount(len(data))
		self.table.setHorizontalHeaderLabels(header)

		if len(data)==0: return
		if dtype=='database':
			for n, key in enumerate(sorted(data.keys())):
				#horHeaders.append(key)
				for m, item in enumerate(data[key]):
					newitem = QTableWidgetItem(item)
					newitem.setData(Qt.EditRole,type(item)(item))
					self.table.setItem(n, m, newitem)
		elif dtype=='queue':
			#self.setSelectionMode(QAbstractItemView.NoSelection)
			total_time = time
			total_time_user = 0
			total_time_marietje = 0
			first_song = True
			for n, key in enumerate(sorted(data.keys())):
				for m, item in enumerate(data[key]):
					if m == 2:  # time column
						if not first_song:
							old_item = item
							item = total_time
							total_time += old_item
							if data[key][3]==self.user:
								total_time_user += old_item
							elif data[key][3]=="marietje":
								total_time_marietje += old_item
							prev_time = old_item
							item = self.format_time(item)
						else:
							prev_time = item
							total_time += item
							if data[key][3]==self.user:
								total_time_user += item
							elif data[key][3]=="marietje":
								total_time_marietje += item
							item = time
							first_song = False
							item = self.format_time(item)
					
					newitem = QTableWidgetItem(item)
					newitem.setData(Qt.EditRole,type(item)(item))
					self.table.setItem(n, m, newitem)

			self.totaltime = total_time - time
			self.totaltime_user = total_time_user
			self.totaltime_marietje = total_time_marietje
			self.queue_empty = (self.totaltime == self.totaltime_marietje)
		self.format_table(data,dtype=dtype)

	def format_table(self,data,dtype='database'):
		if len(data)==0: return
		for row in range(len(data)):
			self.table.setRowHeight(row,17)
			for col in range(0,len(data[data.keys()[0]])):
				if dtype=='database':
					if col==0: self.table.setColumnWidth(0,50)
					elif col==3: self.table.setColumnWidth(3,150)  # 50-3
					else: self.table.setColumnWidth(col,250)
				elif dtype=='queue':
					if col in [0,1]: self.table.setColumnWidth(col,250)
					if col==2: self.table.setColumnWidth(2,50)
					else: self.table.setColumnWidth(3,72)

class MatplotlibWidget(QWidget):
	def __init__(self,parent=None):
		super(MatplotlibWidget,self).__init__(parent)
		self.figure = Figure(figsize=(1,1))
		self.figure.subplots_adjust(left=0.2)
		self.canvas = FigureCanvasQTAgg(self.figure)
		self.axis = self.figure.add_subplot(111,xlim=(0,60),ylim=(0,20))
		self.axis.tick_params(axis='x',labelsize=8)
		self.axis.tick_params(axis='y',labelsize=8)
		self.layoutVertical = QVBoxLayout(self)
		self.layoutVertical.addWidget(self.canvas)
		self.figure.suptitle("Queue Length",fontsize=8)

class UploadThread(QThread):
	progress = pyqtSignal(float)
	def __init__(self,artist,song,user,file_path):
		QThread.__init__(self)
		self.artist = artist
		self.song = song
		self.user = user
		self.file_path = file_path

	def run(self):
		t = time.time()
		with open(self.file_path,'rb') as f:
			m.upload_track(self.artist,self.song,self.user,os.path.getsize(self.file_path),f,update_signal = self.progress)
		self.duration = time.time() - t

class Main:
	def __init__(self,user,data, queue, now_playing, app):
		self.user = user
		self.data = data
		self.queue = queue
		self.now_playing = now_playing
		self.app = app
		self.main_window = MainWindow(self.user,self)
		self.main_window.data = self.data
		self.main_window.total_artists = self.main_window.count_artists(self.data)
		self.main_window.statuslabel.setText("<b>{0}</b> total tracks in database. <b>{1}</b> total artists found (<b>{2:.2f}</b> songs per artist).".format(len(self.main_window.data),self.main_window.total_artists,float(len(self.main_window.data)/float(self.main_window.total_artists))))
		self.main_window.queue_data = self.queue
		self.main_window.now_playing = self.now_playing
		self.main_window.refresh(self.queue,dtype='queue')

		(np_id, stamp, length, time) = m.get_playing()
		for key in self.data.keys():
			if self.data[key][0]==np_id:
				np = self.data[key][1] + u" - " + self.data[key][2]

		self.time_left = length - time + stamp
		mn, se = divmod(int(self.time_left),60)
		ho, mn = divmod(mn, 60)
		tl_formatted = "{0}:{1}:{2}".format(ho,mn,se)
		self.main_window.label3.setText(u"now playing: <b>"+np+"</b> (<i>"+tl_formatted+"</i>)")
		self.main_window.time_left = self.time_left
		self.main_window.np_id = np_id
		self.main_window.show()
		self.main_window.query_bar.setFocus()

def fetch_songs():
	track_list = list()
	uploader_info = {}
	m.uploaders = []
	try:
		f = open("uploader_info.txt",'r')
		lines = f.read().splitlines()
		f.close()
		for l in lines:
			i, u = l.split(':')
			i = int(i.strip())
			u = u.strip()
			uploader_info[i] = u
			if u not in m.uploaders:
				m.uploaders.append(u)
		m.uploaders.sort()
	except:
		pass
	for n,a,s,t in m.list_tracks():
		a = a.decode("utf-8")
		s = s.decode("utf-8")
		if n in uploader_info:
			track_list.append((n,a,s,uploader_info[n]))
		else:
			track_list.append((n,a,s,"Unknown"))
	track_list = dict(enumerate(track_list))
	print("Songs fetched")
	return(track_list)
	
def main(args):
	### MarietjeOld
	parser = optparse.OptionParser()
	username = ''
	password = ''
	parser.add_option('-H', '--host', dest='host',
			  default='noordslet.science.ru.nl',
			  help="Connect to HOST", metavar='HOST')
	parser.add_option('-p', '--port', dest='port',
			  default='1337', type='int',
			  help="Connect on PORT", metavar='PORT')
	parser.add_option('-d', '--directory', dest='userdir',
			  default='.pymarietje',
			  help="Use PATH as userdir", metavar='PATH')
	parser.add_option('-u', '--username', dest='username',
			  help="Account username", metavar='USERNAME')
	(options, args) = parser.parse_args()
	os.environ['ESCDELAY'] = "0";
	

	username = getpass.getuser()
	if not m.check_login(username):
		if os.path.exists("username"):
			with open("username",'r') as f:
				lines = f.read().splitlines()
				line_count = len(lines)
				if(line_count > 0):
					username = lines[0]
				if(line_count > 1):
					password = lines[1]
			if not m.check_login(username):
				raise Exception, "Invalid Username %s" % username
		else:
			username = raw_input("Enter username: ")
			while not m.check_login(username):
				username = raw_input("That user is not in the Marietje database, try again: ")
			password = getpass.getpass("Enter password if you want to refresh the uploader info: ")
	scraper = MarietjeScraper(username, password)
	scraper.refresh_uploader_info()
	queue = m.get_queue()
	data = []
	for a,s,l,r in queue[1]:
		a = a.decode("utf-8")
		s = s.decode("utf-8")
		data.append((a,s,l,r))
	queue = (queue[0], data)
	now_playing = m.get_playing()
	print(now_playing)
	toshow_track_list = fetch_songs()
	time_remaining = queue[0]
	print("Time remaining till next song: {0}".format(time_remaining))
	nqueue = dict(enumerate([list(queue[1][i]) for i in xrange(len(queue[1]))]))
	print(nqueue)
	### QtUI
	app = QApplication(args)
	app.setStyle("cleanlooks")
	main = Main(username,toshow_track_list,nqueue,now_playing,app)
	sys.exit(app.exec_())

if __name__ == '__main__':
	main(sys.argv)
