
# Copyright 2008-2017,2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>


class NavigationModel(object):
	'''This class defines an object that decides how and where to open
	pages, files and other objects in the user interface.
	'''

	def __init__(self, window):
		self.window = window

	def open_page(self, path, anchor=None, new_window=False, anchor_fail_silent=False):
		'''Open a page of the current notebook
		@param path: a page C{Path}
		@param anchor: anchor ID as string
		@param new_window: if C{True} open page in a new window
		@param anchor_fail_silent: if C{True} errors for non-existing anchors ids are surpressed
		'''
		if new_window:
			self.window._uiactions.open_new_window(path, anchor, anchor_fail_silent) # XXX uiactions should call us, not other way around
		else:
			self.window.open_page(path, anchor, anchor_fail_silent)

		return self.window.pageview

	def open_notebook(self, location, pagelink=None):
		'''Open a notebook either in an existing or a new window
		@param location: notebook location as uri or object with "uri" attribute like C{File}, C{Notebook}, or C{NotebookInfo}
		@param pagelink: optional page link (including optional anchor ID) as string or C{Path} object
		'''
		application = self.window.get_application()
		application.open_notebook(location, pagelink)

	def open_manual(self, pagelink=None):
		'''Open the manual either in an existing or a new window
		@param pagelink: optional page link (including optional anchor ID) as string or C{Path} object
		'''
		application = self.window.get_application()
		application.open_manual(pagelink)
