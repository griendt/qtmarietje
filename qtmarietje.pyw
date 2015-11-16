#!/usr/bin/env python
# -*- coding: utf-8 -*-

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

from __future__ import with_statement
import os
import sys
import socket
import threading
import time
import logging
import random
import optparse

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import uic
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg
import matplotlib.pyplot as plt
try: import eyed3
except: pass

import marietje


#############################################################
#
#   PyQt Marietje Client
#   (c) 2015 Alex van de Griendt
#
#   Based on original RawMarietje class by Bas Westerbaan
#
#   
#   Features:
#	- look up queue and database
#	- request tracks under username
#	- look up song id by special query
#	- query randomly selected track
#	- highlight tracks that have been queued previously
#	- upload tracks
#	- detects song metadata when uploading
#
#	Changes in version 0.08:
#	- dunst notification option
#	- fixed graph drawing error
#
#   Changes in version 0.06:
#	- better support for scrolling in queue;
#	- #TODO: still some minor issues present.
#
#   Changes in version 0.051:
#	- minor bugfixes in graph update and display
#
#
#   Changes in version 0.05:
#	- added plot that shows total queue time (blue)
#	  and user queue time (green) over time in minutes.
#
#   Changes in version 0.04:
#	- remembers upload folder for consecutive uploads
#	- checks if song already exists prior to uploading
#	- highlight tracks (red) that are already in queue
#	- highlight tracks (yellow) that are queued by Marietje
#	- highlight tracks (green) that you currently have in queue
#	- fixed double use of timers that caused a core to max out
#
#   Future Plans:
#	- last.fm integrity (scrobbling)
#	- last.fm now_playing artist information display
#	- random statistics about current queue
#	- os.getlogin() only works on UNIX systems
#
#
#############################################################

m = marietje.RawMarietje()

M_VERSION = "0.08"

FormClass, BaseClass = uic.loadUiType("ui.ui")

class MainWindow(FormClass, BaseClass):
	def __init__(self,user,mainobj):
		BaseClass.__init__(self)
		self.setupUi(self)
		
		self.user = user
		
		self.setWindowTitle("QtMarietje %s - Logged in as %s" % (M_VERSION, self.user))
		self.setWindowIcon(QIcon("icon.ico"))
		self.setMinimumSize(800,400)
		self.mainobj = mainobj  # global object
		self.queued_ids = self.get_queued_songs()
		self.time_left = 0
		self.dir_name = ''

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
		
		#self.setCentralWidget(self.table)
		
		text = "Logged in as <b>{0}</b><br><b>F2</b>: Show Help".format(self.user)
		self.label_user.setText(text)

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

		# signals
		self.suggestions = []
		self.query_bar.textChanged.connect(self.perform_query)
		self.query_bar.returnPressed.connect(self.request_track)
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

	'''def resizeEvent(self,resizeEvent):
		h = self.geometry().height()
		self.button_random.move(5,305-400+h)
		self.button_upload.move(105,305-400+h)
		self.label.move(5,355-400+h)
		self.query_bar.move(5,335-400+h)
		self.queue_table.setMaximumHeight(280-400+h)
	'''

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

	def notifyMessage(self):
		try:
			os.system('notify-send -u "low" "Marietje" "Now Playing: {0}"'.format(self.currentSong))
		except:
			self.systemTray.showMessage("Marietje","Currently Playing: %s" % self.currentSong)

	def timer_refresh(self):
		'''Refreshes the screen every 20 seconds to update the queue if the query is empty.'''
		if self.query_bar.text() == '':
			queue = m.get_queue()
			time_left = queue[0]
			self.queue_data = dict(enumerate([list(queue[1][i]) for i in xrange(len(queue[1]))]))
			self.refresh(self.queue_data,dtype='queue')
		
		(np_id, stamp, length, time) = m.get_playing()
		self.time_left = stamp - time + length
		for key in self.data.keys():
			if self.data[key][0]==np_id:
				np = str(self.data[key][1]) + " - " + str(self.data[key][2])

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
				np = str(self.data[key][1]) + " - " + str(self.data[key][2])
				self.currentSong = np

		if self.time_left == 1:
			QTimer.singleShot(6000,self.notifyMessage)

		mn, se = divmod(int(self.time_left),60)
		ho, mn = divmod(mn, 60)
		tl_formatted = "{0}:{1}:{2}".format(str(ho),str(mn).zfill(2),str(se).zfill(2))
		self.label3.setText("now playing: <b>"+np+"</b> (<i>"+tl_formatted+"</i>)")
		if len(self.query_bar.text())<3:
			self.refresh(self.queue_data,dtype='queue')
			self.plotpoints.append(self.queue_table.totaltime/60. - self.queue_table.totaltime_marietje/60. + self.time_left/60.)
			self.plotpoints_user.append(self.queue_table.totaltime_user/60.)
			#self.plotpoints_marietje.append(self.queue_table.totaltime_marietje/60.)
		else:
			self.plotpoints.append(self.plotpoints[-1] - 1/60.)
			self.plotpoints_user.append(max(0,self.plotpoints_user[-1]-1/60.))
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
		if query=='': # show queue
			self.refresh(self.queue_data,dtype='queue')
			
		suggestions = {}

		if str(query).startswith("id:") and len(query)>3:
			for song in self.data:
				if self.data[song][0] == int(query[3:]):
					suggestions[song] = self.data[song]
		else:
			for song in self.data:
				v = str(self.data[song][1]) + " " + str(self.data[song][2])
				if str(query).lower() in str(v).lower():
					suggestions[song]=self.data[song]

		self.suggestions = suggestions

		if query and not str(query).startswith("id:") and len(suggestions) < 1000:
			self.artists = self.count_artists(self.suggestions)
		elif str(query).startswith("id:"):
			self.artists = int(suggestions!=dict())

		if len(suggestions) < 1000:
			self.refresh(self.suggestions)
			if not len(suggestions) == 1: 
				self.statuslabel.setText("<b>{0}</b> results found. <b>{1}</b> unique artists found.".format(len(suggestions),self.artists))
			else: self.statuslabel.setText("<b>1</b> result found. Press <i>Enter</i> to request.")
		else:
			self.refresh(self.queue_data,dtype='queue')
			if not query=='':
				self.statuslabel.setText("Too many (<b>{0}</b>) query results to show!".format(len(suggestions)))
			else: 
				if self.statuslabel.text()=="Request successful!":
					self.timer_refresh()
					pass
				else: 
					text =  "<b>{0}</b> total tracks in database. <b>{1}</b> Total artists found (<b>{2:.2f}</b> songs per artist).".format(len(suggestions),self.total_artists,float(len(suggestions)/float(self.total_artists)))
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
		query = str(self.data[key][1]) + " " + str(self.data[key][2])
		self.query_bar.setText(query)

	def request_track(self):
		if not len(self.suggestions)==1:
			self.statusbar.showMessage("No unique song selected!",5000)
		else:
			m.request_track(self.suggestions.items()[0][1][0],self.user)
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

		(artist,ok) = QInputDialog.getText(self,"Upload Track","Artist Name:",QLineEdit.Normal,af_artist)
		if not ok: return
		(song,ok) = QInputDialog.getText(self,"Upload Track","Song Name:",QLineEdit.Normal,af_title)
		if not ok: return
		print (str(artist),str(song))

		for key in self.data.keys():
			if self.data[key][1] == artist and self.data[key][2] == song:
				errorbox = QMessageBox(self)
				errorbox.setWindowTitle("Track already exists")
				errorbox.setText("A song with id <b>{0}</b> already exists with<br>".format(self.data[key][0])+
				"Artist: <b>{0}</b><br>Title: <b>{1}</b><br><br>Upload will be aborted.".format(artist,song))
				errorbox.show()
				return

		self.upload_song = "%s - %s" % (str(artist),str(song))
		self.statusbar.showMessage("Uploading %s. Progress: 0.0%%" % self.upload_song)
		
		QApplication.processEvents()
		QApplication.processEvents()
		self.upload_thread = UploadThread(artist,song,self.user,file_path)
		self.upload_thread.finished.connect(self.uploaded_track)
		self.upload_thread.progress.connect(self.upload_progress)
		self.upload_thread.start()

	def upload_progress(self,progress):
		if progress < 0.99:
			self.statusbar.showMessage("Uploading %s. Progress: %.1f%%" % (self.upload_song,progress*100),100)
		else:
			self.statusbar.showMessage("Uploading %s. Processing..." % self.upload_song)

	def uploaded_track(self):
		newt = self.upload_thread.duration
		self.statusbar.showMessage("Upload successful after {0:.4f} seconds".format(newt),10000)
		print("Upload successful!")
		self.upload_thread.finished.disconnect()
		self.upload_thread.progress.disconnect()
		self.upload_thread = None

	def refresh(self,data,dtype='database'):
		if self.table.selectedIndexes():
			selectedrow = self.table.selectedIndexes()[0].row()
		else: selectedrow = 0
		#scrolly = self.queue_table.scrollbar.value()
		#scrollvalue = self.queue_table.scrollbar.value()
		#self.queue_table.setParent(None) # old table gets removed by Python garbage collector
		if len(data)==0:
			if dtype=='database':
				self.queue_table.update_table(dict(),['Track ID','Artist','Song','Flags'])
			elif dtype=='queue':
				self.queue_table.update_table(self.queue_data,['1','2','3','4'])
			else:
				print("Unknown table format")
				return
		else:
			if dtype=='database':
				self.queue_table.update_table(data,['Track ID','Artist','Song','Flags'])
			elif dtype=='queue':
				self.queue_table.update_table(data,['Artist','Song','Plays In','By'],dtype='queue',time=self.time_left)
		#self.queue_table.move(5,25)
		#self.setCentralWidget(self.queue_table)
		#self.layout.addWidget(self.queue_table,0,0)
	
		#if selectedrow + 1 == len(data):		# strange scroll display bug fix when selected row is second to last ???
		#	self.queue_table.scrollbar.setValue(9999)
		#else: self.queue_table.scrollbar.setValue(scrolly)  # ensure proper scrolling thing
		self.table.selectRow(selectedrow)

		if dtype=='database':
			try:
				for i in xrange(len(self.data)):
					queued = False
					if int(self.table.item(i,0).text()) in self.queued_ids:
						for j in range(4):
							self.table.item(i,j).setBackground(QColor(220,220,250))
							self.table.item(i,j).setForeground(QColor(50,50,65))
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
				index = self.table.selectedIndexes()[0]
				track_id = int(self.table.model().data(index).toString())			 
				try:
					m.request_track(track_id,self.user)
					self.statusbar.showMessage("Request successful!",5000)
					self.query_bar.setFocus()
					self.queued_ids.append(track_id)
					self.timer_refresh()
				except: pass				
				self.query_bar.setText("")
			elif event.key() in [Qt.Key_F1,Qt.Key_Control,Qt.Key_Shift,Qt.Key_Backspace]:
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
		self.update_table(self.data,['Track ID','Artist','Song','Flags'])
		self.format_table(self.data)
		self.totaltime = 0
		self.totaltime_marietje = 0
		self.queue_empty = True

	def format_time(self,time):
		mn, se = divmod(int(time),60)
		ho, mn = divmod(mn, 60)
		tl_formatted = "{0}:{1}:{2}".format(str(ho),str(mn).zfill(2),str(se).zfill(2))
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
					elif col==3: self.table.setColumnWidth(3,48)  # 50-3
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
				np = str(self.data[key][1]) + " - " + str(self.data[key][2])

		self.time_left = length - time + stamp
		mn, se = divmod(int(self.time_left),60)
		ho, mn = divmod(mn, 60)
		tl_formatted = "{0}:{1}:{2}".format(ho,mn,se)
		self.main_window.label3.setText("now playing: <b>"+np+"</b> (<i>"+tl_formatted+"</i>)")
		self.main_window.time_left = self.time_left
		self.main_window.np_id = np_id
		self.main_window.show()
		self.main_window.query_bar.setFocus()

def fetch_songs():
	track_list = list()
	for track in m.list_tracks():
		track_list.append(track)
	track_list = dict(enumerate(track_list))
	print("Songs fetched")
	return(track_list)
	
def main(args):
	### MarietjeOld
	parser = optparse.OptionParser()
	username = ''
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
	

	# if not "getlogin" in dir(os) or not m.check_login(os.getlogin()):
	if not m.check_login(username):
		if os.path.exists("username"):
			with open("username",'r') as f:
				username = f.read().splitlines()[0]
			if not m.check_login(username):
				raise Exception, "Invalid Username %s" % username
		else:
			username = raw_input("Enter username: ")
			while not m.check_login(username):
				username = raw_input("That user is not in the Marietje database, try again: ")
	queue = m.get_queue()
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
