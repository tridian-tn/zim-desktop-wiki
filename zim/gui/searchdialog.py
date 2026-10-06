
# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# Tests: search gui.TestDialogs.testSearchDialog

from gi.repository import Gtk
import logging

from zim.notebook import Path
from zim.gui.widgets import Dialog, BrowserTreeView, InputEntry, ErrorDialog, ScrolledWindow, StatusPage

from zim.search import *


logger = logging.getLogger('zim.gui.searchdialog')


HELP_TEXT = _(
	'For advanced search you can use operators like\n'
	'AND, OR and NOT. See the help page for more details.'
) # T: help text for the search dialog


class SearchDialog(Dialog):

	READY = 0
	SEARCHING = 1
	DONE = 2
	CANCELLED = 3

	def __init__(self, widget, notebook, page, navigation):
		Dialog.__init__(self, widget, _('Search'), # T: Dialog title
			buttons=Gtk.ButtonsType.CLOSE, help='Help:Searching',
			defaultwindowsize=(400, 300)
		)
		self.page = page

		hbox = Gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False, True, 0)
		search_label = Gtk.Label.new_with_mnemonic(_('_Search') + ': ')
		hbox.pack_start(search_label, False, True, 0) # T: input label
		self.query_entry = InputEntry()
		self.query_entry.set_tooltip_text(HELP_TEXT)
		hbox.add(self.query_entry)
		search_label.set_mnemonic_widget(self.query_entry)
		self.search_button = Gtk.Button.new_with_mnemonic(_('_Find')) # T: Button label
		hbox.pack_start(self.search_button, False, True, 0)

		self.spinner = Gtk.Spinner()
		hbox.pack_start(self.spinner, False, True, 0)

		self.cancel_button = Gtk.Button.new_with_mnemonic(_('_Cancel')) # T: Button label
		hbox.pack_start(self.cancel_button, False, True, 0)

		self.namespacecheckbox = Gtk.CheckButton.new_with_mnemonic(_('_Limit search to the current page and sub-pages'))
			# T: checkbox option in search dialog
		if page is None:
			self.namespacecheckbox.set_sensitive(False)

		self.matchcasecheckbox = Gtk.CheckButton.new_with_mnemonic(_('Match c_ase')) # T: checkbox option in search dialog
		self.wholewordcheckbox = Gtk.CheckButton.new_with_mnemonic(_('Whole _word')) # T: checkbox option in search dialog

		self.uistate.setdefault('search_flags', '')
		self._set_flags(SearchFlag.from_letters(self.uistate['search_flags'] or ''))

		for widget in (self.namespacecheckbox, self.matchcasecheckbox, self.wholewordcheckbox):
			self.vbox.pack_start(widget, False, True, 0)

		self.results_treeview = SearchResultsTreeView(notebook, navigation)
		self._stack = Gtk.Stack()
		for name, widget in (
			('ready', StatusPage('edit-find-symbolic', None, HELP_TEXT)),
			('searching', StatusPage('edit-find-symbolic', _('Searching ...'))), # T: placeholder label when search has started
			('no-results', StatusPage('edit-find-symbolic', _('No results'), HELP_TEXT)), # T: placeholder label when search has no results
			('results', ScrolledWindow(self.results_treeview)),
		):
			widget.show_all()
			self._stack.add_named(widget, name)
		self.vbox.pack_start(self._stack, True, True, 0)

		self.search_button.connect_object('clicked', self.__class__._search, self)
		self.cancel_button.connect_object('clicked', self.__class__._cancel, self)
		self.query_entry.connect_object('activate', self.__class__._search, self)

		self._set_state(self.READY)

	def save_uistate(self):
		self.uistate['search_flags'] = self._get_flags().to_letters()

	def search(self, query):
		'''Trigger a search to be performed.
		Because search can take a long time to execute it is best to
		call this method after the dialog is shown.

		@param query: the query as string
		'''
		self.query_entry.set_text(query)
		self._search()

	def _set_flags(self, flags):
		self.matchcasecheckbox.set_active(SEARCH_CASE_SENSITIVE in flags)
		self.wholewordcheckbox.set_active(SEARCH_WHOLE_WORD in flags)

	def _get_flags(self):
		flags = SearchFlag(0)
		if self.matchcasecheckbox.get_active():
			flags |= SEARCH_CASE_SENSITIVE
		if self.wholewordcheckbox.get_active():
			flags |= SEARCH_WHOLE_WORD
		return flags

	def _search(self):
		string = self.query_entry.get_text()
		if self.namespacecheckbox.get_active():
			assert self.page is not None
			string = 'Section: "%s" and (%s)' % (self.page.name, string)

		flags = self._get_flags()

		self._set_state(self.SEARCHING)
		try:
			self.results_treeview.search(string, flags, self._set_show_results)
		except Exception as error:
			ErrorDialog(self, error).run()

		if not self.results_treeview.cancelled:
			self._set_state(self.DONE)
		else:
			self._set_state(self.CANCELLED)

	def _cancel(self):
		self.results_treeview.cancelled = True

	def _set_state(self, state):
		def hide(button):
			button.hide()
			button.set_no_show_all(True)

		def show(button):
			button.set_no_show_all(False)
			button.show_all()

		if state in (self.READY, self.DONE, self.CANCELLED):
			self.query_entry.set_sensitive(True)
			hide(self.cancel_button)
			if self.spinner:
				self.spinner.stop()
				hide(self.spinner)
			show(self.search_button)
			if state == self.READY:
				self._stack.set_visible_child_name('ready')
			elif len(self.results_treeview.get_model()):
				self._stack.set_visible_child_name('results')
			else:
				self._stack.set_visible_child_name('no-results')
		elif state == self.SEARCHING:
			self.query_entry.set_sensitive(False)
			hide(self.search_button)
			if self.spinner:
				show(self.spinner)
				self.spinner.start()
			show(self.cancel_button)
			self._stack.set_visible_child_name('searching')
		else:
			assert False, 'BUG: invalid state'

	def _set_show_results(self):
		self._stack.set_visible_child_name('results')



class SearchResultsTreeView(BrowserTreeView):

	NAME_COL = 0
	SCORE_COL = 1
	PATH_COL = 2

	def __init__(self, notebook, navigation):
		model = Gtk.ListStore(str, int, object)
			# NAME_COL, SCORE_COL, PATH_COL
		BrowserTreeView.__init__(self, model)
		self.navigation = navigation
		self.query = None
		self._page_search = PageSearch(notebook, self._search_callback)
		self.cancelled = False

		cell_renderer = Gtk.CellRendererText()
		for name, i in (
			(_('Page'), 0), # T: Column header search dialog
			(_('Score'), 1), # T: Column header search dialog
		):
			column = Gtk.TreeViewColumn(name, cell_renderer, text=i)
			column.set_sort_column_id(i)
			if i == 0:
				column.set_expand(True)
			self.append_column(column)

		model.set_sort_column_id(self.SCORE_COL, Gtk.SortType.DESCENDING)

		self.connect('row-activated', self._do_open_page)
		self.connect('destroy', self.__class__._cancel)

	def _cancel(self):
		self.cancelled = True

	def _search_callback(self):
		if Gtk.events_pending():
			Gtk.main_iteration_do(False)

		if self.cancelled:
			raise SearchCancelledException

	def search(self, query, flags, set_show_results_cb=None):
		query = query.strip()
		if not query:
			return
		logger.info('Searching for: %s', query)

		self.cancelled = False
		self.query = self._page_search.parse_page_search_query(query, flags)
		logger.debug('Parsed query: %s', self.query)

		model = self.get_model()
		if not model:
			return

		model.clear()
		it = self._page_search.search_pages(self.query)
		try:
			result = next(it)
		except StopIteration:
			return
		else:
			# Handle first with cb
			model.append((result.path.name, result.search_score, result.path))
					# FUTURE - use result.search_snippets
			if set_show_results_cb:
				set_show_results_cb()

			# Iter through rest without cb
			for result in it:
				model.append((result.path.name, result.search_score, result.path))
					# FUTURE - use result.search_snippets

	def _do_open_page(self, view, path, col):
		page = Path(self.get_model()[path][0])
		pageview = self.navigation.open_page(page)

		# Popup find dialog with same query
		if pageview and self.query:
			fquery = self._page_search.find_query_from_search_query(self.query)
			if fquery:
				pageview.show_find(fquery, highlight=True)
