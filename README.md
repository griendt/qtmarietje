# qtmarietje
Marietje client based on PyQt


  PyQt Marietje Client
  (c) 2015 Alex van de Griendt

  Based on original RawMarietje class by Bas Westerbaan
  https://github.com/marietje/marietje

  Features:
	- look up queue and database
	- request tracks under username
	- look up song id by special query
	- query randomly selected track
	- highlight tracks that have been queued previously or are in queue
	- upload tracks
	- detects song metadata when uploading

	Changes in version 0.08:
	- uses notify-send when available
	- fixed graph drawing bug

  Changes in version 0.06:
	- better support for scrolling in queue

  Changes in version 0.051:
	- minor bugfixes in graph update and display

  Changes in version 0.05:
	- added plot that shows total queue time (blue)
	  and user queue time (green) over time in minutes.

  Changes in version 0.04:
	- remembers upload folder for consecutive uploads
	- checks if song already exists prior to uploading
	- highlight tracks (red) that are already in queue
	- highlight tracks (yellow) that are queued by Marietje
	- highlight tracks (green) that you currently have in queue
	- fixed double use of timers that caused a core to max out

  Future Plans:
	- last.fm integrity (scrobbling)
	- last.fm now_playing artist information display
	- random statistics about current queue
	- os.getlogin() only works on UNIX systems



