
# Copyright 2012-2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests

from tests.config import EnvironmentConfigContext, ConfigManager

import sys
import io as StringIO
import threading
import time


from zim.main import *

import zim
import zim.main


from zim.notebook.info import NotebookInfo


class capture_stdout:

		def __enter__(self):
			self.real_stdout = sys.stdout
			sys.stdout = StringIO.StringIO()
			return sys.stdout

		def __exit__(self, type, value, traceback):
			sys.stdout = self.real_stdout


class TestParseCommand(tests.TestCase):

	def runTest(self):
		for command, klass in list(zim.main.commands.items()):
			obj = zim.main.build_command(['--%s' % command])
			self.assertIsInstance(obj, klass)

		obj = zim.main.build_command(['-v'])
		self.assertIsInstance(obj, VersionCommand)

		obj = zim.main.build_command(['-h'])
		self.assertIsInstance(obj, HelpCommand)

		obj = zim.main.build_command(['foo'])
		self.assertIsInstance(obj, GuiCommand)

		obj = zim.main.build_command(['--plugin', 'quicknote'])
		self.assertIsInstance(obj, Command)

		obj = zim.main.build_command(['--server', '--gui'])
		self.assertIsInstance(obj, ServerGuiCommand)


class TestVersion(tests.TestCase):

	def runTest(self):
		cmd = VersionCommand('version')
		with capture_stdout() as output:
			cmd.run()
		self.assertTrue(output.getvalue().startswith('zim'))


class TestHelp(tests.TestCase):

	def runTest(self):
		cmd = HelpCommand('help')
		with capture_stdout() as output:
			cmd.run()
		self.assertTrue(output.getvalue().startswith('usage:'))


class TestNotebookCommand(tests.TestCase):

	cmd_class = NotebookCommand

	def get_cmd(self, *args):
		cmd = self.cmd_class('gui')
		cmd.arguments = ('NOTEBOOK', '[PAGE]')
		cmd.parse_options(*args)
		return cmd

	def testPWDhandling(self):
		# check if PWD at "parse_options" is remembered after changing dir
		cmd = self.get_cmd('./Notes')

		pwd = os.getcwd()
		self.addCleanup(os.chdir, pwd)
		os.chdir('/')

		myinfo = NotebookInfo(pwd + '/Notes')
		notebookinfo, page = cmd.get_notebook_argument()
		self.assertEqual(notebookinfo, myinfo)

	#def testNotebookName(self):
	#	pass

	def testFile(self):
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('Foo.txt')
		file.touch()

		for arg in (file.path, file.uri):
			cmd = self.get_cmd(arg)
			myinfo = NotebookInfo(file.path)
			notebookinfo, page = cmd.get_notebook_argument()
			self.assertEqual(notebookinfo, myinfo)
			notebook, href = cmd.build_notebook()
			self.assertEqual(notebook.uri, folder.uri)
			self.assertEqual(href.names, 'Foo')

		# Test override by page argument
		cmd = self.get_cmd(file.path, 'Bar')
		notebook, href = cmd.build_notebook()
		self.assertEqual(notebook.uri, folder.uri)
		self.assertEqual(href.names, 'Bar')

	def testNotebookZimFile(self):
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		config = folder.file('notebook.zim')
		config.touch()

		for arg in (config.path, config.uri):
			cmd = self.get_cmd(arg)
			myinfo = NotebookInfo(config.path)
			notebookinfo, page = cmd.get_notebook_argument()
			self.assertEqual(notebookinfo, myinfo)
			notebook, href = cmd.build_notebook()
			self.assertEqual(notebook.uri, folder.uri)
			self.assertIsNone(href)

	def testNestedNotebookZimFile(self):
		# Test specific case where parent folder also is a notebook - as in bug #2189
		parentfolder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		parentfolder.file('notebook.zim').touch()
		folder = parentfolder.folder('MyNotebook')
		config = folder.file('notebook.zim')
		config.touch()

		for arg in (config.path, config.uri):
			cmd = self.get_cmd(arg)
			myinfo = NotebookInfo(config.path)
			notebookinfo, page = cmd.get_notebook_argument()
			self.assertEqual(notebookinfo, myinfo)
			notebook, href = cmd.build_notebook()
			self.assertEqual(notebook.uri, folder.uri)
			self.assertIsNone(href)



class TestGuiCommand(TestNotebookCommand):

	cmd_class = GuiCommand


class TestGuiStart(tests.TestCase):

	## TODO: test default notebook logic when no argument

	def setUp(self):
		file = ConfigManager.get_config_file('notebooks.list')
		file.remove()

	def runTest(self):
		from zim.gui.mainwindow import MainWindow

		## Without argument should prompt
		def testAddNotebookDialog(dialog):
			self.assertIn(dialog.__class__.__name__,
				('AddNotebookDialog', 'NotebookDialog')
			)

		cmd = GuiCommand('gui')
		with tests.DialogContext(testAddNotebookDialog):
			cmd.run() # Exits without running due to no notebook given in dialog

		### Try again with argument
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		folder.touch()

		cmd = GuiCommand('gui')
		cmd.parse_options(folder.path)
		with tests.WindowContext(MainWindow):
			with tests.LoggingFilter('zim', 'Exception while loading plugin:'):
				window = cmd.run()
				self.addCleanup(window.destroy)

		self.assertEqual(window.__class__.__name__, 'MainWindow')
		self.assertEqual(window.notebook.uri, folder.uri)
		self.assertGreaterEqual(len(ConfigManager.preferences['General']['plugins']), 3)
		self.assertGreaterEqual(len(window.pageview.__zim_extension_objects__), 3)

		with tests.WindowContext(MainWindow):
			window2 = cmd.run()
		self.assertIs(window2, window)
			# Ensure repeated calling gives unique window


class TestGuiListCommand(tests.TestCase):

	# NotebookDialog has it's own't test cases, which also cover the
	# AddNotebookDialog and prompt_notebook, so here we can mock it and
	# just test it is called properly from the command class

	def setUp(self):
		from zim.notebook import NotebookInfo

		self.folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		self.folder.touch()

		import zim.gui.notebookdialog
		orig = zim.gui.notebookdialog.prompt_notebook
		def restore():
			zim.gui.notebookdialog.prompt_notebook = orig
		self.addCleanup(restore)

		def mock():
			return NotebookInfo(self.folder.uri, name='Test')

		zim.gui.notebookdialog.prompt_notebook = mock

	def runTest(self):
		from zim.gui.mainwindow import MainWindow

		cmd = GuiCommand('gui')
		cmd.parse_options('--list')

		with tests.WindowContext(MainWindow):
			with tests.LoggingFilter('zim', 'Exception while loading plugin:'):
				window = cmd.run()
				self.addCleanup(window.destroy)


class TestManual(tests.TestCase):

	def runTest(self):
		from zim.gui.mainwindow import MainWindow

		cmd = ManualCommand('manual')
		with tests.WindowContext(MainWindow):
			with tests.LoggingFilter('zim', 'Exception while loading plugin:'):
				window = cmd.run()
				self.addCleanup(window.destroy)

		self.assertEqual(window.__class__.__name__, 'MainWindow')


@tests.slowTest
class TestServer(tests.TestCase):

	def runTest(self):
		from urllib.request import urlopen
		from urllib.error import URLError

		dir = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		dir.touch()
		cmd = ServerCommand('server')
		cmd.parse_options(dir.path)
		t = threading.Thread(target=cmd.run)
		t.start()

		for i in range(30):
			try:
				re = urlopen('http://localhost:8080')
				self.assertEqual(re.getcode(), 200)
				break
			except URLError:
				time.sleep(1) # give more time to startup server
		else:
			assert False, 'Failed to start server within 10 seconds'

		cmd.server.shutdown()
		t.join()


class TestServerGui(tests.TestCase):

	def runTest(self):
		cmd = ServerGuiCommand('server')
		window = cmd.run()
		self.addCleanup(window.destroy)
		self.assertEqual(window.__class__.__name__, 'ServerWindow')


@tests.verySlowTest
class TestConvertNotebookCommand(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(mock=tests.MOCK_ALWAYS_REAL, content=tests.FULL_NOTEBOOK)

		cmd = ConvertNotebookCommand('convert-notebook')
		cmd.parse_options('--format=markdown', notebook.folder.path)
		with tests.LoggingFilter('zim', '!!!'):
			cmd.run()

		self.assertTrue(notebook.folder.file('roundtrip.md').exists())
		config = notebook.folder.file('notebook.zim').read()
		self.assertIn('default_file_format=markdown', config)
		self.assertIn('default_file_extension=.md', config)


## ExportCommand() is tested in tests/export.py

## SearchCommand() is tested in tests./search.py

import os

class TestZimScript(tests.TestCase):

	def testEnvironINI(self):
		# Ensure restoring old environment
		orig_environ = os.environ.copy()
		def restore_environ():
			os.environ.clear()
			os.environ.update(orig_environ)
		self.addCleanup(restore_environ)

		# Setup tmp file
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		folder.touch()

		# Import the script - which is not a module ...
		globals = {}
		scriptfile = 'zim.py'
		with open(scriptfile) as f:
			code = compile(f.read(), scriptfile, 'exec')
			exec(code, globals)
		init_environment = globals['init_environment']

		# Test missing file is silent, and no chance to data dir
		os.environ['XDG_DATA_DIRS'] = 'TEST'
		init_environment(folder.path)
		self.assertEqual(os.environ['XDG_DATA_DIRS'], 'TEST')

		# Test with existing data dir
		data_dir = folder.folder('share')
		data_dir.touch()
		init_environment(folder.path)
		self.assertEqual(os.environ['XDG_DATA_DIRS'], 'TEST' + os.pathsep + os.path.normpath(data_dir.path))

		# Test with packaged dir in "_internal"
		os.environ['XDG_DATA_DIRS'] = 'TEST'
		int_data_dir = folder.folder('_internal/share')
		int_data_dir.touch()
		init_environment(folder.path)
		self.assertEqual(os.environ['XDG_DATA_DIRS'], 'TEST' + os.pathsep + os.path.normpath(data_dir.path)
				+ os.pathsep + os.path.normpath(int_data_dir.path))

		# Setup file
		file = folder.file('environ.ini')
		file.write(
			'[Environment]\n'
			'MYHOME=../home\n'
			'MYPATH=${PATH}' + os.pathsep + './bin\n'
		)
		# write tmp file
		# 	- abs path
		#   - rel path
		#   - os.pathsep

		# Test with file in place
		init_environment(folder.path)
		self.assertEqual(os.environ['MYHOME'], os.path.normpath(folder.parent().folder('home').path))
		self.assertEqual(os.environ['MYPATH'], os.environ['PATH'] + os.pathsep + os.path.normpath(folder.folder('bin').path))
