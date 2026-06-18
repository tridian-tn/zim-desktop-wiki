
# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module defines the search path for zim config files following
the freedesktop.org (XDG) Base Dir specification.
'''

import os
import logging

from zim.newfs import LocalFile, LocalFolder


logger = logging.getLogger('zim.config')


# Lot of `try ... except ...` here because failure crashes the application before it gets into the main loop
def _get_environ_folder(value: str|None, default: str):
	if value and value.strip():
		try:
			return LocalFolder(value.strip())
		except:
			logger.warning("Invalid folder in XDG environ: %s", p)

	# Fallback if no value or folder object failed
	try:
		return LocalFolder(default)
	except:
		logger.warning("Invalid folder in XDG environ: %s", p)


def _split_environ_dir_list(value: str|None, default: tuple):
	paths = [p for p in value.strip().split(os.pathsep) if p] if value else ()

	folders = []
	for p in paths:
		try:
			folders.append(LocalFolder(p))
		except:
			logger.warning("Invalid folder in XDG environ: %s", p)

	# Fallback if not value or all folder objects failed
	if not folders:
		for p in default:
			try:
				folders.append(LocalFolder(p))
			except:
				pass

	return folders


## Initialize config paths

ZIM_DATA_DIR = None #: 'data' dir relative to script file (when running from source), L{LocalFolder} or C{None}
XDG_DATA_HOME = None #: L{LocalFolder} for XDG data home
XDG_DATA_DIRS = None #: list of L{LocalFolder} objects for XDG data dirs path
XDG_CONFIG_HOME = None #: L{LocalFolder} for XDG config home
XDG_CONFIG_DIRS = None #: list of L{LocalFolder} objects for XDG config dirs path
XDG_CACHE_HOME = None #: L{LocalFolder} for XDG cache home
XDG_TEMPLATES_DIR = None #: L{LocalFolder} for XDG templates dir


def set_basedirs(_ignore_test=False):
	'''This method sets the global configuration paths for according to the
	freedesktop basedir specification.
	Called automatically when module is first loaded, should be
	called explicitly only when environment has changed.
	'''
	global ZIM_DATA_DIR
	global XDG_DATA_HOME
	global XDG_DATA_DIRS
	global XDG_CONFIG_HOME
	global XDG_CONFIG_DIRS
	global XDG_CACHE_HOME
	global XDG_TEMPLATES_DIR

	# Cast string to folder
	import zim
	try:
		zim_data_dir = LocalFile(zim.ZIM_EXECUTABLE).parent().folder('data')
	except:
		logger.warning('Could not access data folder for: %r', zim.ZIM_EXECUTABLE)
	if zim_data_dir.exists():
		ZIM_DATA_DIR = zim_data_dir

	if os.name == 'nt':
		APPDATA = os.environ['APPDATA']

		XDG_DATA_HOME = _get_environ_folder(os.environ.get('XDG_DATA_HOME'), APPDATA + r'\zim\data')

		XDG_DATA_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_DATA_DIRS'), ('~/.local/share/',)) # Backwards compatibility

		XDG_CONFIG_HOME = _get_environ_folder(os.environ.get('XDG_CONFIG_HOME'), APPDATA + r'\zim\config')

		XDG_CONFIG_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_CONFIG_DIRS'), ('~/.config/',)) # Backwards compatibility

		XDG_CACHE_HOME = _get_environ_folder(os.environ.get('XDG_CACHE_HOME'), APPDATA + r'\zim\cache')

		XDG_TEMPLATES_DIR = _get_environ_folder(os.environ.get('XDG_TEMPLATES_DIR'), APPDATA + r'\zim\file_templates')
	else:
		XDG_DATA_HOME = _get_environ_folder(os.environ.get('XDG_DATA_HOME'), '~/.local/share/')

		XDG_DATA_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_DATA_DIRS'), ('/usr/share/', '/usr/local/share/'))

		XDG_CONFIG_HOME = _get_environ_folder(os.environ.get('XDG_CONFIG_HOME'), '~/.config/')

		XDG_CONFIG_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_CONFIG_DIRS'), ('/etc/xdg/',))

		XDG_CACHE_HOME = _get_environ_folder(os.environ.get('XDG_CACHE_HOME'), '~/.cache')

		XDG_TEMPLATES_DIR = _get_environ_folder(os.environ.get('XDG_TEMPLATES_DIR'), '~/Templates')
			# TODO: we should try to query xdg-user-dirs to get this value, for now at least allow customization via the environment

		if os.environ.get('ZIM_TEST_RUNNING') and not _ignore_test:
			# See tests/__init__.py, we load more folders then we really want
			# because the needs of Gtk, but want to restrict it here for all
			# zim internal use
			XDG_DATA_DIRS = [LocalFolder(os.environ['TEST_XDG_DATA_DIRS'])]

# Call on module initialization to set defaults
set_basedirs()


def log_basedirs():
	'''Write the search paths used to the logger, used to generate
	debug output
	'''
	if ZIM_DATA_DIR:
		logger.debug('Running from a source dir: "%s"', ZIM_DATA_DIR.parent())
	else:
		logger.debug('Not running from a source dir')
	logger.debug('Set XDG_DATA_HOME to: "%s"', XDG_DATA_HOME)
	logger.debug('Set XDG_DATA_DIRS to: (%s)', ', '.join('"%s"' % d for d in XDG_DATA_DIRS))
	logger.debug('Set XDG_CONFIG_HOME to: "%s"', XDG_CONFIG_HOME)
	logger.debug('Set XDG_CONFIG_DIRS to: (%s)', ', '.join('"%s"' % d for d in XDG_CONFIG_DIRS))
	logger.debug('Set XDG_CACHE_HOME to: "%s"', XDG_CACHE_HOME)
